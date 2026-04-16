// trayIconsManager.js — manages legacy XEmbed tray icons (X11 only).

import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Signals from 'resource:///org/gnome/shell/misc/signals.js';

import * as IndicatorStatusIcon from './indicatorStatusIcon.js';
import * as SettingsManager from './settingsManager.js';
import * as Util from './util.js';

let _instance = null;

export class TrayIconsManager extends Signals.EventEmitter {
    static initialize() {
        if (!_instance)
            _instance = new TrayIconsManager();
        return _instance;
    }

    static destroy() {
        if (_instance)
            _instance.destroy();
    }

    constructor() {
        super();
        if (_instance)
            throw new Error('TrayIconsManager already exists');

        this._changedId = SettingsManager.getDefaultGSettings().connect(
            'changed::legacy-tray-enabled', () => this._toggle());
        this._toggle();
    }

    _toggle() {
        if (SettingsManager.getDefaultGSettings().get_boolean('legacy-tray-enabled'))
            this._enable();
        else
            this._disable();
    }

    _enable() {
        if (this._tray)
            return;
        this._tray = new Shell.TrayManager();
        Util.connectSmart(this._tray, 'tray-icon-added', this, this._onTrayIconAdded);
        Util.connectSmart(this._tray, 'tray-icon-removed', this, this._onTrayIconRemoved);
        this._tray.manage_screen(Main.panel);
    }

    _disable() {
        if (!this._tray)
            return;
        IndicatorStatusIcon.getTrayIcons().forEach(i => i.destroy());
        this._tray = null;
    }

    _onTrayIconAdded(_tray, icon) {
        const trayIcon = new IndicatorStatusIcon.IndicatorStatusTrayIcon(icon);
        IndicatorStatusIcon.addIconToPanel(trayIcon);
    }

    _onTrayIconRemoved(_tray, icon) {
        try {
            const [trayIcon] = IndicatorStatusIcon.getTrayIcons().filter(
                i => i._icon === icon);
            if (trayIcon)
                trayIcon.destroy();
        } catch (e) {
            Util.Logger.warn(`No container found for ${icon.title}`);
        }
    }

    destroy() {
        this.emit('destroy');
        SettingsManager.getDefaultGSettings().disconnect(this._changedId);
        this._disable();
        _instance = null;
    }
}
