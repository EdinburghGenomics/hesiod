#!/bin/bash
set -eu

# Wrapper for GraphicsMagick that makes images with text
# Usage gm_label.sh <size> <text> <filename>
_size="$1"
_text="$2"
_out="$3"

/lustre/software/graphicsmagick/GraphicsMagick-1.3.28/bin/gm convert -pointsize 20 -background lightblue1 -fill black \
    -font /usr/share/fonts/dejavu/DejaVuSansMono-BoldOblique.ttf \
    label:"$_text" -background lightblue1 -extent "$_size" "$_out"
