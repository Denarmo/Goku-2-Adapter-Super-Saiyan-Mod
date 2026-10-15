PY ?= python3
BASE ?= firmware/NS36_V3.4.bin

all: mods

# vendor image + enabled C mods from mods/
mods:
	$(PY) tools/modkit.py build --base $(BASE) -o build/NS36_mod.bin

test: mods
	$(PY) tools/emu_test.py build/NS36_mod.bin

info:
	$(PY) tools/ns36fw.py info $(BASE)

decompile:
	bash tools/decompile.sh $(BASE)

clean:
	rm -rf build

.PHONY: all mods test info decompile clean
