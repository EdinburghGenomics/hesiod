import os, sys, re
from pprint import pprint
import threading
from collections import deque

import pystray
from PIL import Image, ImageDraw, ImageFont

"""The pstray library is a bit jank. But it does seem to do the job. To get
   it working:

   1) Install python3-gi
   2) Make a VEnv with 'pystray' and 'vext'
   3) Also install 'vext.gi'

   This script demonstrates a periodically changing icon with an option
   to exit.
"""

# We need some images, and we have the whole of the PIL to play with.
# Can I generate images from emoji? Why yes, I can!
# See https://github.com/python-pillow/Pillow/pull/4955

_font_cache = dict()
def image_from_emoji(char="U+1F346", size=None):
    """Use PIL to generate an image from any emoji character
    """
    # Convert the character code to actual char
    if len(char) > 1:
        char = re.sub(r"^U\+", "0x", char)
        char = chr(int(char, 0))

    fontfile = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
    fontsize = 109 # The magic size that works for the Noto fonts.
    try:
        font = _font_cache[(fontfile,fontsize)]
    except KeyError:
        font = ImageFont.truetype(fontfile,
                                  size = fontsize,
                                  layout_engine = ImageFont.LAYOUT_RAQM)
        _font_cache[(fontfile,fontsize)] = font
    char_displaysize = font.getsize(char)

    # Make a square image large enough for the character.
    img_size = (max(char_displaysize), max(char_displaysize))
    img = Image.new('RGBA', img_size)
    draw = ImageDraw.Draw(img)

    # Centre the image in the square
    offset = tuple((si-sc)//2 for si, sc in zip(img_size, char_displaysize))
    assert all(o>=0 for o in offset)

    # adjust offset, half value is right size for height axis.
    draw.text((offset[0], offset[1]//2), char, font=font, embedded_color=True, fill='#000')

    # if requested, scale the image to size
    if size:
        img.thumbnail(size)

    return img


def make_menu():
    """If you don't have any menu the icon won't display!
    """
    def click_exit(icon, item):
        # We need to kill the event thread...
        icon.timeout.set()
        icon.stop()

    def click_status(icon,item):
        # Actually we don't do anything here
        pass

    return pystray.Menu(
            pystray.MenuItem( 'Last sync: 1 minute',
                              click_status ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem( 'Exit',
                              click_exit ) )

def event_loop(icons, sleep_time=5):

    icon_deque = deque(icons.values())

    def _callback(icon):
        """Update the status every 5 seconds
        """
        # This provides an interruptable timer
        icon.timeout = threading.Event()

        # We always need to do this...
        icon.visible = True

        while True:
            if icon.timeout.wait(timeout=sleep_time):
                # We were rudely interrupted - exit!
                return

            print("Updating status...")

            icon_deque.rotate(-1)
            icon.icon = icon_deque[0]

    return _callback

def main():

    # Specify some icons:
    icons = dict( sunny = "U+1F60E",
                  worry = "U+1F61F",
                  skull = "U+1F480" )

    # Convert icon codes to PIL images
    for i in icons:
        icons[i] = image_from_emoji(icons[i])

    icon = pystray.Icon('test name', menu=make_menu(), icon=icons['sunny'])
    icon.run(setup=event_loop(icons=icons))

if __name__ == '__main__':
    main()
