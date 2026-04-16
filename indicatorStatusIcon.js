// indicatorStatusIcon.js — renders SNI items as clickable icons for the tray.

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as Panel from 'resource:///org/gnome/shell/ui/panel.js';

import * as AppIndicator from './appIndicator.js';
import * as DBusMenu from './dbusMenu.js';
import * as SettingsManager from './settingsManager.js';
import * as Util from './util.js';

const DEFAULT_ICON_SIZE = Panel.PANEL_ICON_SIZE || 16;

// The extension sets this handler so icons get routed into the tray popup
// instead of being added individually to the panel's status area.
let _customIconHandler = null;

export function setCustomIconHandler(handler) {
    _customIconHandler = handler;
}

/**
 * Called by the protocol layer (statusNotifierWatcher) when a new icon appears.
 * Routes it through our custom handler if set, otherwise falls back to panel.
 */
export function addIconToPanel(statusIcon) {
    if (_customIconHandler) {
        _customIconHandler(statusIcon);
        return;
    }

    // Fallback: add directly to panel (shouldn't happen when extension is active).
    const indicatorId = `appindicator-${statusIcon.uniqueId}`;
    const currentIcon = Main.panel.statusArea[indicatorId];
    if (currentIcon) {
        if (currentIcon !== statusIcon)
            currentIcon.destroy();
        Main.panel.statusArea[indicatorId] = null;
    }

    const settings = SettingsManager.getDefaultGSettings();
    Main.panel.addToStatusArea(indicatorId, statusIcon, 1,
        settings.get_string('tray-pos'));
}

export function getTrayIcons() {
    return Object.values(Main.panel.statusArea).filter(
        i => i instanceof IndicatorStatusTrayIcon
    );
}

// ---------------------------------------------------------------------------
// BaseStatusIcon — shared base for both modern and legacy icon types.
// util.js imports this for tryCleanupOldIndicators().
// ---------------------------------------------------------------------------
export const BaseStatusIcon = GObject.registerClass(
class BaseStatusIcon extends PanelMenu.Button {
    // Marker class so util.js can identify our icons in the panel.
});

// ---------------------------------------------------------------------------
// IndicatorStatusIcon — modern SNI icon (AppIndicator / KStatusNotifierItem)
// ---------------------------------------------------------------------------
export const IndicatorStatusIcon = GObject.registerClass(
class IndicatorStatusIcon extends BaseStatusIcon {
    _init(indicator) {
        super._init(0.5, indicator.accessibleName);
        this._indicator = indicator;

        this._box = new St.BoxLayout({style_class: 'panel-status-indicators-box'});
        this.add_child(this._box);

        // Icon actor.
        this._icon = new AppIndicator.IconActor(indicator, DEFAULT_ICON_SIZE);
        this._box.add_child(this._icon);

        // Apply opacity from settings.
        this._updateOpacity();

        // Connect indicator signals.
        Util.connectSmart(this._indicator, 'ready', this, () => this._sync());
        Util.connectSmart(this._indicator, 'menu', this, () => this._updateMenu());
        Util.connectSmart(this._indicator, 'label', this, () => this._updateLabel());
        Util.connectSmart(this._indicator, 'status', this, () => this._updateStatus());
        Util.connectSmart(this._indicator, 'accessible-name', this,
            () => this.set_accessible_name(this._indicator.accessibleName));
        Util.connectSmart(this._indicator, 'destroy', this, () => this.destroy());

        const settings = SettingsManager.getDefaultGSettings();
        Util.connectSmart(settings, 'changed::icon-opacity', this, () => this._updateOpacity());

        this.connect('notify::visible', () => this._updateMenu());

        this._sync();

        // Set up the menu (DBusMenu integration).
        if (this.menu)
            this.menu.closeOnSelect = false;
    }

    get uniqueId() {
        return this._indicator.uniqueId;
    }

    isReady() {
        return this._indicator && this._indicator.isReady;
    }

    _sync() {
        if (!this.isReady())
            return;
        this._updateLabel();
        this._updateStatus();
        this._updateMenu();
    }

    _updateStatus() {
        this.visible = this._indicator.status !== AppIndicator.SNIStatus.PASSIVE;
    }

    _updateLabel() {
        const {label} = this._indicator;
        if (label) {
            if (!this._label || !this._labelBin) {
                this._labelBin = new St.Bin({yAlign: Clutter.ActorAlign.CENTER});
                this._label = new St.Label();
                this._labelBin.set_child(this._label);
                this._box.add_child(this._labelBin);
            }
            this._label.set_text(label);
        } else if (this._label) {
            this._labelBin.destroy();
            this._labelBin = null;
            this._label = null;
        }
    }

    _updateMenu() {
        if (this._menuClient) {
            this._menuClient.disconnect(this._menuReadyId);
            this._menuClient.destroy();
            this._menuClient = null;
            this.menu.removeAll();
        }

        if (this.visible && this._indicator.menuPath) {
            this._menuClient = new DBusMenu.Client(
                this._indicator.busName,
                this._indicator.menuPath,
                this._indicator
            );

            if (this._menuClient.isReady)
                this._menuClient.attachToMenu(this.menu);

            this._menuReadyId = this._menuClient.connect('ready-changed', () => {
                if (this._menuClient.isReady)
                    this._menuClient.attachToMenu(this.menu);
                else
                    this._updateMenu();
            });
        }
    }

    _updateOpacity() {
        const settings = SettingsManager.getDefaultGSettings();
        const userValue = settings.get_user_value('icon-opacity');
        this.opacity = userValue ? userValue.unpack() : 255;
    }

    _onDestroy() {
        if (this._menuClient) {
            this._menuClient.disconnect(this._menuReadyId);
            this._menuClient.destroy();
            this._menuClient = null;
        }
        if (super._onDestroy)
            super._onDestroy();
    }

    // -- Input handlers -------------------------------------------------------

    vfunc_button_press_event(event) {
        const button = event.get_button();

        // Middle-click → secondary activate (e.g. play/pause).
        if (button === Clutter.BUTTON_MIDDLE) {
            this._indicator.secondaryActivate(
                event.get_time(), ...event.get_coords());
            return Clutter.EVENT_STOP;
        }

        // Left-click → activate (show/hide window) OR open menu if ItemIsMenu.
        if (button === Clutter.BUTTON_PRIMARY) {
            if (this._indicator.supportsActivation &&
                !this._indicator._proxy?.ItemIsMenu) {
                this._indicator.open(...event.get_coords(), event.get_time());
                return Clutter.EVENT_STOP;
            }
        }

        // Left-click (menu-only apps) or right-click → open DBusMenu popup.
        if (button === Clutter.BUTTON_PRIMARY || button === Clutter.BUTTON_SECONDARY) {
            if (this.menu && this.menu.numMenuItems > 0)
                this.menu.toggle();
            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    vfunc_scroll_event(event) {
        if (event.get_scroll_direction() === Clutter.ScrollDirection.SMOOTH) {
            const [dx, dy] = event.get_scroll_delta();
            this._indicator.scroll(dx, dy);
            return Clutter.EVENT_STOP;
        }
        return Clutter.EVENT_PROPAGATE;
    }
});

// ---------------------------------------------------------------------------
// IndicatorStatusTrayIcon — legacy XEmbed tray icons (X11 only)
// ---------------------------------------------------------------------------
export const IndicatorStatusTrayIcon = GObject.registerClass(
class IndicatorStatusTrayIcon extends BaseStatusIcon {
    _init(icon) {
        super._init(0.5, icon.wm_class, {dontCreateMenu: true});
        this._icon = icon;

        this._box = new St.BoxLayout({style_class: 'panel-status-indicators-box'});
        this.add_child(this._box);
        this._box.add_child(icon);

        this.add_style_class_name('appindicator-icon');
        this.add_style_class_name('tray-icon');

        this.connect('button-press-event', (_actor, _event) => {
            this.add_style_pseudo_class('active');
            return Clutter.EVENT_PROPAGATE;
        });
        this.connect('button-release-event', (_actor, event) => {
            this._icon.click(event);
            this.remove_style_pseudo_class('active');
            return Clutter.EVENT_PROPAGATE;
        });

        Util.connectSmart(this._icon, 'destroy', this, () => {
            icon.clear_effects();
            this.destroy();
        });

        const settings = SettingsManager.getDefaultGSettings();
        Util.connectSmart(settings, 'changed::icon-size', this, () => this._updateIconSize());

        const themeContext = St.ThemeContext.get_for_stage(global.stage);
        Util.connectSmart(themeContext, 'notify::scale-factor', this, () => this._updateIconSize());

        this._updateIconSize();
    }

    get uniqueId() {
        return `legacy:${this._icon.wm_class}:${this._icon.pid}`;
    }

    isReady() {
        return !!this._icon;
    }

    _updateIconSize() {
        const settings = SettingsManager.getDefaultGSettings();
        const {scaleFactor} = St.ThemeContext.get_for_stage(global.stage);
        let iconSize = settings.get_int('icon-size');
        if (iconSize <= 0)
            iconSize = DEFAULT_ICON_SIZE;
        this._icon.set({
            width: iconSize * scaleFactor,
            height: iconSize * scaleFactor,
            xAlign: Clutter.ActorAlign.CENTER,
            yAlign: Clutter.ActorAlign.CENTER,
        });
    }
});
