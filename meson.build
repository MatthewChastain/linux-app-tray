project('linux-app-tray', 'c', version: '0.1.0')

python = import('python').find_installation('python3')

install_subdir('src', install_dir: join_paths(get_option('prefix'), 'share/linux-app-tray'))
install_data(
  'data/linux-app-tray.desktop',
  'data/org.linuxapptray.Settings.gschema.xml',
  'data/style.css',
  install_dir: join_paths(get_option('prefix'), 'share/linux-app-tray/data')
)
