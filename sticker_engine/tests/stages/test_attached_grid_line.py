import numpy as np
from PIL import Image, ImageDraw
from sticker_engine.stages.postprocess import normalize_solid_background


def test_grid_line_touching_outline_preserves_foreground():
    im=Image.new('RGBA',(240,240),(170,245,240,255));d=ImageDraw.Draw(im)
    d.rectangle((0,0,239,5),fill='white')
    d.rectangle((105,6,134,45),fill='white')
    d.rectangle((110,11,129,39),fill='black')
    before=np.array(im);after=np.array(normalize_solid_background(im))
    assert np.array_equal(after[6:46,103:137],before[6:46,103:137])
    assert tuple(after[2,30])==(170,245,240,255)
    assert tuple(after[2,115])==(255,255,255,255)


def test_wide_edge_connected_white_clothing_is_not_a_divider():
    im=Image.new('RGBA',(240,240),(170,245,240,255));d=ImageDraw.Draw(im)
    d.rectangle((0,190,239,239),fill=(224,224,224,255))
    d.rectangle((0,235,239,239),fill='white')
    before=np.array(im);after=np.array(normalize_solid_background(im))
    assert np.array_equal(after[190:],before[190:])


def test_short_rim_decoration_is_preserved():
    im=Image.new('RGBA',(240,240),(170,245,240,255));d=ImageDraw.Draw(im)
    d.line((20,2,70,2),fill='white',width=3)
    before=np.array(im);after=np.array(normalize_solid_background(im))
    assert np.array_equal(after[:6],before[:6])


def test_attached_two_axis_grid_leaves_no_corner_fragment():
    im=Image.new('RGBA',(240,240),(170,245,240,255));d=ImageDraw.Draw(im)
    d.rectangle((0,0,239,5),fill='white');d.rectangle((0,0,3,239),fill='white')
    d.rectangle((105,6,134,45),fill='white');d.rectangle((110,11,129,39),fill='black')
    after=np.array(normalize_solid_background(im))
    assert tuple(after[1,1])==(170,245,240,255)
    assert tuple(after[25,115])==(0,0,0,255)


def test_detached_grid_above_nearby_head_does_not_leave_white_dash():
    im=Image.new('RGBA',(240,240),(170,245,240,255));d=ImageDraw.Draw(im)
    d.rectangle((0,0,239,5),fill='white')
    d.rectangle((105,10,134,45),fill='white');d.rectangle((110,15,129,39),fill='black')
    before=np.array(im);after=np.array(normalize_solid_background(im))
    assert tuple(after[2,115])==(170,245,240,255)
    assert np.array_equal(after[10:46,105:135],before[10:46,105:135])
