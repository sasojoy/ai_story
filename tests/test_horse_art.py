"""馬的圖（Joy 2026-10-17）：每種毛色、兩匹名駒各一個鍵；網頁只對 web/ 裡真的有檔的鍵放圖。"""

import server
from tianxia import mounts
from tianxia.state import Equipment


def _horse(name, template=None):
    return Equipment(id="騎:1", slot="mount", name=name, kind="馬", tier=1, quality="下品", attribute="快", template=template)


def test_every_coat_and_named_steed_has_its_own_picture():
    assert set(mounts.COAT_ART) == set(mounts.COATS)
    assert len(set(mounts.COAT_ART.values()) | set(mounts.STEED_ART.values())) == 8
    assert mounts.art_of(_horse("青驄駒")) == "qingcong"
    assert mounts.art_of(_horse("踏霜駒", "tashuang_ju")) == "tashuang"
    assert mounts.art_of(_horse("無名")) == ""


def test_only_pictures_on_disk_are_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WEB", tmp_path)
    assert server.horse_art() == []
    (tmp_path / "horse-zaoliu.webp").write_bytes(b"x")
    assert server.horse_art() == ["zaoliu"]
