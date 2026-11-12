# Old Ledger — генератор изображений

Генерирует картинки персонажа «Old Ledger» через OpenAI Image API
(модели `gpt-image-2.5-flare` и `gpt-image-2.5-sunburst`).

## Установка

Нужен Python 3.9+.

```bash
cd old-ledger
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Куда положить ключ

1. Создайте ключ на https://platform.openai.com/api-keys (нужен пополненный баланс;
   для моделей GPT Image OpenAI может попросить верификацию организации).
2. Скопируйте `.env.example` в `.env` и вставьте ключ:

   ```
   OPENAI_API_KEY=sk-ваш-ключ
   ```

Файл `.env` уже в `.gitignore` — он не попадёт в git. Не вставляйте ключ в код.

## Запуск

```bash
python generate.py --prompt main --count 6
python generate.py --prompt sheet --count 2
python generate.py --prompt emotions --count 2
```

Картинки сохраняются в `output/<имя_промпта>/001.png`, `002.png`, …
Нумерация продолжается, старые файлы не перезаписываются.

Перед генерацией скрипт показывает примерную стоимость и спрашивает подтверждение.
`--yes` — без вопроса, `--dry-run` — только показать стоимость.

### Референс (чтобы персонаж был одинаковым)

Выберите удачную картинку и передайте её как референс:

```bash
python generate.py --prompt emotions --count 2 --reference output/main/003.png
```

`--reference` можно указать несколько раз (до 16 картинок). С референсом по умолчанию
используется более точная модель `gpt-image-2.5-sunburst` (цена та же).

### Другие опции

| Опция | Значение |
|---|---|
| `--quality low/medium/high` | качество (по умолчанию `medium`) |
| `--size 1536x864` | свой размер (стороны кратны 16, пропорции от 1:3 до 3:1) |
| `--model ...` | другая модель, например `gpt-image-2.5-sunburst` |

## Промпты

Все промпты и размеры лежат в `prompts.json` — редактируйте без изменения кода.
Можно добавить новый ключ (например `"office_night"`), и он сразу станет доступен
в `--prompt`.

Размеры по умолчанию: `main` — 1536x864 (16:9), `sheet` и `emotions` — 1536x1024 (широкий).

Негативный промпт хранится в `prompts.json`, но **не отправляется**: у OpenAI Image API
нет такого параметра.

## Примерная стоимость (medium)

| Промпт | Размер | ~за 1 картинку |
|---|---|---|
| main | 1536x864 | ~$0.016 |
| sheet / emotions | 1536x1024 | ~$0.019 |

`low` примерно в 2 раза дешевле, `high` примерно в 4 раза дороже. Это оценка: OpenAI
считает по токенам. Точную сумму смотрите в https://platform.openai.com/usage.
