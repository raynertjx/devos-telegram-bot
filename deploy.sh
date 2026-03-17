#!/bin/bash
cd /home/ubuntu/devos-telegram-bot
git pull origin main
docker compose up -d --build
