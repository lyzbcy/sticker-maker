import numpy as np
from PIL import Image, ImageDraw
from sticker_engine.stages.grid_cutter import cut_grid


def test_same_color_preserves_full_frame_and_caption_space(tmp_path):
    im = Image.new('RGB', (400, 400), (206, 232, 255)); draw = ImageDraw.Draw(im)
    for y in (0, 200):
        for x in (0, 200):
            draw.rectangle((x+30, y+15, x+170, y+160), fill=(50, 60, 70))
    source = tmp_path/'grid.png'; im.save(source)
    paths, notes = cut_grid(source, 2, tmp_path/'out', preserve_cell=True)
    for p in paths:
        panel = Image.open(p)
        assert panel.size == (200, 200)
        assert panel.getpixel((100, 199)) == (206, 232, 255)
        assert np.all(np.array(panel)[164:] == (206, 232, 255))
    assert '整格保留' in notes[0]


def test_near_grid_color_boundary_preserves_uneven_tiles(tmp_path):
    im = Image.new('RGB', (400, 400)); draw = ImageDraw.Draw(im)
    colors = [(255,210,210), (210,255,210), (210,210,255), (255,245,180)]
    boxes = [(0,0,209,189),(210,0,399,189),(0,190,209,399),(210,190,399,399)]
    for box,color in zip(boxes,colors): draw.rectangle(box,fill=color)
    p=tmp_path/'grid.png';im.save(p)
    panels,_=cut_grid(p,2,tmp_path/'out',preserve_cell=True)
    for path,box,color in zip(panels,boxes,colors):
        a=np.array(Image.open(path)); assert tuple(a[0,0])==color
        assert np.all(a==color)
        assert a.shape[:2] == (box[3]-box[1]+1,box[2]-box[0]+1)


def test_character_edge_is_not_a_grid_boundary(tmp_path):
    im=Image.new('RGB',(400,400),'#cfe8ff');d=ImageDraw.Draw(im)
    # Sharp silhouette inside the allowed search band but not full-span.
    d.rectangle((180,40,185,100),fill='black')
    p=tmp_path/'grid.png';im.save(p)
    paths,_=cut_grid(p,2,tmp_path/'out',preserve_cell=True)
    assert all(Image.open(p).size==(200,200) for p in paths)
