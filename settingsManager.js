// Settings manager — provides GSettings access to protocol-layer modules.
//
// Supports two import styles:
//   import * as SettingsManager from './settingsManager.js';
//     -> SettingsManager.getDefaultGSettings() / .SettingsManager.initialize()
//   import {SettingsManager} from './settingsManager.js';
//     -> SettingsManager.getDefaultGSettings() / .initialize()

let _settings = null;

export function getDefaultGSettings() {
    return _settings;
}

export class SettingsManager {
    static initialize(extension) {
        _settings = extension.getSettings();
    }

    static destroy() {
        _settings = null;
    }

    static getDefaultGSettings() {
        return _settings;
    }
}
