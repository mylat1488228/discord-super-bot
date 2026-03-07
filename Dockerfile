# Используем легкую версию Python 3.10
FROM python:3.10-slim

# 1. ПРИНУДИТЕЛЬНО устанавливаем FFmpeg и звуковые драйверы
RUN apt-get update && \
    apt-get install -y ffmpeg libopus-dev git && \
    rm -rf /var/lib/apt/lists/*

# 2. Создаем рабочую папку
WORKDIR /app

# 3. Копируем твои файлы в контейнер
COPY . .

# 4. Обновляем pip и устанавливаем библиотеки
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 5. Запускаем бота
CMD ["python", "main.py"]
