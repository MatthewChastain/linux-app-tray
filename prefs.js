import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';
import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class LinuxAppTrayPreferences extends ExtensionPreferences {
    getPreferencesWidget() {
        const settings = this.getSettings();
        const box = new Gtk.Box({
            orientation: Gtk.Orientation.VERTICAL,
            spacing: 12,
            margin_start: 24, margin_end: 24,
            margin_top: 24, margin_bottom: 24,
        });

        // -- Tray position --
        const posBox = this._row(box, 'Tray position in panel');
        const posWidget = new Gtk.ComboBoxText();
        posWidget.append('left', 'Left');
        posWidget.append('center', 'Center');
        posWidget.append('right', 'Right');
        settings.bind('tray-pos', posWidget, 'active-id', Gio.SettingsBindFlags.DEFAULT);
        posBox.append(posWidget);

        // -- Icon size --
        const sizeBox = this._row(box, 'Icon size (0 = panel default)');
        const sizeWidget = new Gtk.SpinButton();
        sizeWidget.set_range(0, 96);
        sizeWidget.set_increments(1, 4);
        sizeWidget.set_value(settings.get_int('icon-size'));
        sizeWidget.connect('value-changed', w =>
            settings.set_int('icon-size', w.get_value_as_int()));
        sizeBox.append(sizeWidget);

        // -- Icon opacity --
        const opacityBox = this._row(box, 'Icon opacity (0-255)');
        const opacityWidget = new Gtk.SpinButton();
        opacityWidget.set_range(0, 255);
        opacityWidget.set_increments(5, 25);
        opacityWidget.set_value(settings.get_int('icon-opacity'));
        opacityWidget.connect('value-changed', w =>
            settings.set_int('icon-opacity', w.get_value_as_int()));
        opacityBox.append(opacityWidget);

        // -- Arrow direction --
        const arrowBox = this._row(box, 'Chevron arrow direction');
        const arrowWidget = new Gtk.ComboBoxText();
        arrowWidget.append('down', 'Down');
        arrowWidget.append('up', 'Up');
        arrowWidget.append('left', 'Left');
        arrowWidget.append('right', 'Right');
        settings.bind('arrow-direction', arrowWidget, 'active-id',
            Gio.SettingsBindFlags.DEFAULT);
        arrowBox.append(arrowWidget);

        // -- Close on activate --
        const closeBox = this._row(box, 'Close tray after activating an icon');
        const closeWidget = new Gtk.Switch({halign: Gtk.Align.END});
        settings.bind('close-on-activate', closeWidget, 'active',
            Gio.SettingsBindFlags.DEFAULT);
        closeBox.append(closeWidget);

        // -- Legacy tray --
        const legacyBox = this._row(box, 'Enable legacy XEmbed tray icons (X11)');
        const legacyWidget = new Gtk.Switch({halign: Gtk.Align.END});
        settings.bind('legacy-tray-enabled', legacyWidget, 'active',
            Gio.SettingsBindFlags.DEFAULT);
        legacyBox.append(legacyWidget);

        return box;
    }

    _row(parent, labelText) {
        const row = new Gtk.Box({
            orientation: Gtk.Orientation.HORIZONTAL,
            spacing: 12,
        });
        const label = new Gtk.Label({
            label: labelText,
            hexpand: true,
            halign: Gtk.Align.START,
        });
        row.append(label);
        parent.append(row);
        return row;
    }
}
