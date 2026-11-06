#!/bin/zsh
# 双击启动「豚说小豚」桌面宠物
cd "$(dirname "$0")"

PY="/Users/zhuan/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

exec "$PY" "$PWD/tunshuo_pet_pro.py"
