// Settings manager — provides GSettings access to protocol-layer modules.
// The protocol files (appIndicator.js etc.) call getDefaultGSettings().

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
}
