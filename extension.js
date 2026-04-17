// extension.js — Linux App Tray: Windows-style collapsible system tray for GNOME.
//
// Groups all StatusNotifierItem (AppIndicator) icons behind a single chevron
// button in the panel. Click the chevron to expand/collapse the icon row.

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import * as StatusNotifierWatcher from './statusNotifierWatcher.js';
import * as Interfaces from './interfaces.js';
import * as TrayIconsManager from './trayIconsManager.js';
import * as IndicatorStatusIcon from './indicatorStatusIcon.js';
import * as Util from './util.js';
import {SettingsManager} from './settingsManager.js';

export default class LinuxAppTrayExtension extends Extension {
    constructor(metadata) {
        super(metadata);

        Util.Logger.init(this);
        Interfaces.initialize(this);

        this._isEnabled = false;
        this._trayButton = null;
        this._trayIcons = new Map(); // id → IndicatorStatusIcon
        this._statusNotifierWatcher = null;
        this._watchDog = new Util.NameWatcher(StatusNotifierWatcher.WATCHER_BUS_NAME);
        this._watchDog.connect('vanished', () => this._maybeEnableWatcher());
    }

    enable() {
        this._isEnabled = true;
        SettingsManager.initialize(this);

        // Clean up any stale indicators from a previous session.
        Util.tryCleanupOldIndicators(IndicatorStatusIcon.BaseStatusIcon);

        // Intercept new icons into our tray instead of the panel.
        IndicatorStatusIcon.setCustomIconHandler(icon => this._addIcon(icon));

        this._createTrayButton();
        this._maybeEnableWatcher();
        TrayIconsManager.TrayIconsManager.initialize();

        // Pick up any icons already in the panel from ubuntu-appindicators etc.
        this._adoptExistingIcons();
    }

    disable() {
        this._isEnabled = false;

        // Disconnect setting handlers.
        if (this._arrowDirChangedId) {
            SettingsManager.getDefaultGSettings().disconnect(this._arrowDirChangedId);
            this._arrowDirChangedId = 0;
        }

        IndicatorStatusIcon.setCustomIconHandler(null);
        TrayIconsManager.TrayIconsManager.destroy();

        if (this._statusNotifierWatcher) {
            this._statusNotifierWatcher.destroy();
            this._statusNotifierWatcher = null;
        }

        // Safely destroy all tracked icons.
        const snapshot = new Map(this._trayIcons);
        this._trayIcons.clear();
        for (const [, icon] of snapshot) {
            if (icon.get_parent())
                icon.get_parent().remove_child(icon);
            icon.destroy();
        }

        if (this._trayButton) {
            this._trayButton.destroy();
            this._trayButton = null;
        }

        SettingsManager.destroy();
    }

    // -----------------------------------------------------------------------
    // Tray button: a single panel button with a chevron + popup row of icons
    // -----------------------------------------------------------------------

    _createTrayButton() {
        this._trayButton = new PanelMenu.Button(0.0, 'LinuxAppTray', false);

        const settings = SettingsManager.getDefaultGSettings();

        // Chevron icon — direction configurable via settings.
        const directionToIcon = {
            'up': 'pan-up-symbolic',
            'down': 'pan-down-symbolic',
            'left': 'pan-start-symbolic',
            'right': 'pan-end-symbolic',
        };
        const initialDir = settings.get_string('arrow-direction') || 'down';
        this._chevron = new St.Icon({
            icon_name: directionToIcon[initialDir] || 'pan-down-symbolic',
            style_class: 'system-status-icon',
        });
        this._trayButton.add_child(this._chevron);

        // Update chevron when the setting changes.
        this._arrowDirChangedId = settings.connect('changed::arrow-direction', () => {
            const dir = settings.get_string('arrow-direction') || 'down';
            this._chevron.icon_name = directionToIcon[dir] || 'pan-down-symbolic';
        });

        // Popup content: a horizontal box of icons inside a menu section.
        this._trayBox = new St.BoxLayout({
            style: 'padding: 4px; spacing: 4px;',
        });
        const trayItem = new PopupMenu.PopupBaseMenuItem({reactive: false});
        trayItem.add_child(this._trayBox);

        const section = new PopupMenu.PopupMenuSection();
        section.addMenuItem(trayItem);
        this._trayButton.menu.addMenuItem(section);
        this._trayButton.menu.closeOnSelect = false;

        // Keep the popup open while an icon's submenu is active.
        this._trayButton.menu._submenuOpen = false;
        const origClose = this._trayButton.menu.close.bind(this._trayButton.menu);
        this._trayButton.menu.close = (animate) => {
            if (!this._trayButton.menu._submenuOpen)
                origClose(animate);
        };

        // Add to the panel.  KEEP the menu in menuManager so GNOME Shell
        // properly grabs input when the popup is open — otherwise clicks
        // on tray icons inside the popup pass through to whatever is
        // behind it.  (Panel hot-switch to neighbouring buttons is a minor
        // cost compared to a totally non-interactive popup.)
        Main.panel.addToStatusArea('linux-app-tray', this._trayButton, 1,
            settings.get_string('tray-pos'));
    }

    // -----------------------------------------------------------------------
    // Icon management: add / remove icons from the tray popup
    // -----------------------------------------------------------------------

    _addIcon(icon) {
        const id = icon.uniqueId || 'unknown';
        if (this._trayIcons.has(id))
            return;

        // Reparent the icon widget into our tray box.
        if (icon.get_parent())
            icon.get_parent().remove_child(icon);

        // Wrap the icon in a reactive PopupBaseMenuItem so GNOME Shell's
        // popup menu event system routes mouse events to it. The popup menu
        // only dispatches events properly to PopupBaseMenuItem children —
        // raw actors get bypassed by the menu's key/mouse handling.
        const wrapper = new PopupMenu.PopupBaseMenuItem({
            reactive: true,
            activate: false,      // we handle activation inside the icon
            can_focus: true,
            hover: true,
        });
        wrapper.add_child(icon);

        // Forward the wrapper's click into the icon's own press handler
        // (preserves button detection: primary / secondary / middle).
        wrapper.connect('button-press-event', (_w, event) => {
            return icon.vfunc_button_press_event
                ? icon.vfunc_button_press_event(event)
                : Clutter.EVENT_PROPAGATE;
        });
        wrapper.connect('scroll-event', (_w, event) => {
            return icon.vfunc_scroll_event
                ? icon.vfunc_scroll_event(event)
                : Clutter.EVENT_PROPAGATE;
        });

        // Track submenu state so the tray stays open during interaction.
        // Close the tray after a menu item is activated (if the setting is on).
        if (icon.menu) {
            icon.menu.connect('open-state-changed', (_menu, isOpen) => {
                if (this._trayButton)
                    this._trayButton.menu._submenuOpen = isOpen;
                if (!isOpen) {
                    const settings = SettingsManager.getDefaultGSettings();
                    if (settings.get_boolean('close-on-activate'))
                        this._trayButton.menu.close();
                }
            });
        }

        // Clean up when the icon is destroyed (app exits).
        icon.connect('destroy', () => {
            const w = this._trayIcons.get(id);
            if (w) {
                if (w.get_parent() === this._trayBox)
                    this._trayBox.remove_child(w);
                if (!w.is_finalized?.()) {
                    try { w.destroy(); } catch (_e) {}
                }
                this._trayIcons.delete(id);
            }
        });

        this._trayIcons.set(id, wrapper);
        this._trayBox.add_child(wrapper);
    }

    // Grab any icons that are already in the panel (e.g. from a previously
    // active extension or from the session bus before we started).
    _adoptExistingIcons() {
        const existing = Object.entries(Main.panel.statusArea).filter(
            ([key, val]) => key.startsWith('appindicator-') &&
                val instanceof IndicatorStatusIcon.IndicatorStatusIcon
        );
        for (const [key, icon] of existing) {
            if (icon.get_parent())
                icon.get_parent().remove_child(icon);
            this._addIcon(icon);
            delete Main.panel.statusArea[key];
        }
    }

    // -----------------------------------------------------------------------
    // StatusNotifierWatcher lifecycle
    // -----------------------------------------------------------------------

    _maybeEnableWatcher() {
        if (!this._isEnabled || this._statusNotifierWatcher)
            return;
        if (this._watchDog.nameAcquired && this._watchDog.nameOnBus)
            return;

        this._statusNotifierWatcher = new StatusNotifierWatcher.StatusNotifierWatcher(
            this._watchDog);
    }
}
