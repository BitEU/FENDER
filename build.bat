python -m PyInstaller --onefile --windowed --icon=assets/car.ico --add-data "decoders;decoders" --add-data "src;src" --add-data "assets/car.ico;assets" --hidden-import="tkinterdnd2" --hidden-import="decoders.denso_decoder" --hidden-import="decoders.bmw_decoder" --hidden-import="decoders.stellantis_decoder" --hidden-import="decoders.mercedes_decoder" --hidden-import="decoders.honda_decoder" --hidden-import="decoders.onstar_decoder" --hidden-import="decoders.toyota_decoder" --hidden-import="src.core.base_decoder" --hidden-import="src.gui.main_window" --hidden-import="src.cli.cli_interface" --hidden-import="src.utils.file_operations" --hidden-import="src.utils.system_info" main.py