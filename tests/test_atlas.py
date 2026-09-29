from tianxia.atlas import region_of


def test_locations_belong_to_the_region_that_contains_them(content):
    assert region_of(content, "town").id == "north"
    assert region_of(content, "cave").id == "north"
    content.locations["lake"].y = 170  # 移進南區的多邊形
    assert region_of(content, "lake").id == "south"


def test_location_outside_every_region_goes_to_the_nearest(content):
    content.locations["lake"].y = 197  # 南區只畫到 y=190：兩區之外，離南區最近
    assert region_of(content, "lake").id == "south"
    content.locations["lake"].y = 200  # 地圖最下緣：還是南區最近
    assert region_of(content, "lake").id == "south"


def test_no_regions_means_no_region(content):
    content.map.regions = []
    assert region_of(content, "town") is None
