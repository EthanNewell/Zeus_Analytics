#!/bin/sh
# Клипы для фильма из чистой записи сервиса (NOCAP=1 node presentation/video.mjs → film/footage.webm).
# Начало и длина каждого клипа — по отметкам шагов в marks.json, с запасом в полсекунды.
set -e
cd "$(dirname "$0")"
rm -rf clips
while read -r name start dur; do
  mkdir -p "clips/$name"
  ffmpeg -nostdin -loglevel error -y -ss "$start" -i footage.webm -t "$dur" -vf fps=30 -q:v 3 "clips/$name/%04d.jpg"
done <<LIST
login 1.2 4.8
passport 25.4 9.0
registry 42.4 13.0
card 56.0 24.5
review 87.0 13.3
map 127.2 6.2
quality 138.4 7.0
LIST
