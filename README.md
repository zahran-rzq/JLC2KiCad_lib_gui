# JLC2KiCad - KiCad GUI Plugin

This repository is a simple KiCad plugin GUI wrapper.

## Installation

1. In PCB Editor, open `Tools -> External Plugins -> Open Plugin Directory`.
2. Clone this repository:

```bash
git clone https://github.com/dzid26/JLC2KiCad_lib_gui.git
```

3. Launch Kicad and PCB Editor
On first launch you will be asked to install JLC2KiCadLib in KiCad's Python environment.


4. In KiCad PCB Editor, click `Tools -> External Plugins -> Refresh Plugins`.


## Upgrade JLC2KiCad library

In-app update:

- Open the plugin dialog and click `Check for updates`.


If needed, you can install/update manually, e.g.:

```bash
git pull
"c:/Program Files/KiCad/9.0/bin/python.exe" -m pip install --upgrade JLC2KiCadLib
```

## Output folder (GUI)

- Di dialog plugin sekarang ada field `Output folder` + tombol `Browse...`.
- Jika isi path relatif, path akan dianggap relatif terhadap folder project KiCad aktif.
- Jika folder belum ada, plugin akan membuatnya otomatis.

## Menjalankan JLC2KiCad secara manual

### 1) Cek CLI resmi dari library JLC2KiCadLib

Gunakan ini untuk melihat syntax dan argumen terbaru sesuai versi yang terpasang:

```bash
"c:/Program Files/KiCad/9.0/bin/python.exe" -m JLC2KiCadLib --help
```

Jika command di atas tidak tersedia pada versi tertentu, cek package detail:

```bash
"c:/Program Files/KiCad/9.0/bin/python.exe" -m pip show JLC2KiCadLib
```

### 2) Manual lewat API plugin (stabil untuk flow plugin ini)

Di wrapper ini, fungsi yang dipakai adalah:

```python
download_part(component_id, out_dir, get_symbol=False, skip_existing=False)
```

Argumen:

- `component_id`: nomor part JLC/LCSC, contoh `C326215`
- `out_dir`: folder output tujuan
- `get_symbol`: `True` untuk ikut generate symbol
- `skip_existing`: `True` untuk melewati file yang sudah ada

Contoh pemakaian minimal dari Python KiCad:

```python
from JLC2KiCad_gui import download_part

libpath, component_name = download_part(
	component_id="C326215",
	out_dir=r"D:/kicad/libs/JLC2KiCad_lib",
	get_symbol=True,
	skip_existing=True,
)

print(libpath, component_name)
```
