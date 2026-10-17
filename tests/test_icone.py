"""O ícone da aba do navegador é quadrado (o logo largo ficava esticado)."""
from __future__ import annotations

import struct
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
ASSINATURA_PNG = bytes.fromhex("89504e470d0a1a0a")


def test_icone_da_aba_e_quadrado_e_usado_nas_paginas():
    png = (WEB / "public/icone.png").read_bytes()
    assert png[:8] == ASSINATURA_PNG
    largura, altura = struct.unpack(">II", png[16:24])
    assert largura == altura and largura >= 64
    assert 'icon: "/icone.png"' in (WEB / "app/layout.tsx").read_text(encoding="utf-8")
