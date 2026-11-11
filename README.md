# Проверка ROS 2 через WireGuard

Два независимых Docker Compose стека: **Client1 — receiver** (`10.10.0.4`),
**Client2 — sender** (`10.10.0.3`). Можно запустить на двух компьютерах или
на одном: у стеков разные Compose-проекты, Docker-сети и сетевые пространства.

Каждый стек поднимает WireGuard из своего файла в `wg/`, а ROS-контейнер
использует сетевое пространство этого туннеля. Cyclone DDS привязан к `wg0`,
multicast отключён, discovery идёт на явный WG-адрес второго клиента.
Перед запуском ROS проверяется маршрут до второго клиента: только через
`wg0`, с ожидаемым исходящим IP. Порты на хост не публикуются.

Путь сообщений:

```text
Client2 sender → wg0 10.10.0.3 → WireGuard-сервер → wg0 10.10.0.4 → Client1 receiver
              ← подтверждения с SHA-256 по той же WG-сети ←
```

Используется ROS 2 Jazzy, Python/rclpy и надёжный QoS (`RELIABLE`).
Образ `resources/Canon80D_8_8_12800_printer_14_real.jpg` читается OpenCV как
NumPy-массив `uint8 BGR` и передаётся через `cv_bridge` в `sensor_msgs/msg/Image`
с кодировкой `bgr8`: 512×512×3, 786432 байта пикселей на сообщение.
Это передача массива пикселей, без JPEG-сжатия в ROS. На диске receiver сохраняет
PNG без потерь. Сравнивается SHA-256 пикселей, а не байтов JPEG и PNG.

## Запуск

Нужны Docker Engine с Compose v2+ либо запущенный Docker Desktop с Linux-контейнерами.
WireGuard-контейнеру нужны `NET_ADMIN` и `/dev/net/tun` в Linux-хосте/VM Docker.
`wg-quick` использует модуль ядра, а при его отсутствии — `wireguard-go`.

На WireGuard-сервере должна быть разрешена маршрутизация между клиентами
`10.10.0.3` и `10.10.0.4`, включая UDP для DDS. Обоим клиентам уже разрешена
подсеть `10.10.0.0/24` в предоставленных конфигах. Настройки самого сервера
здесь отсутствуют, поэтому пересылку между клиентами нужно проверить при запуске.
Клиентские ключи из этих конфигов не должны одновременно использоваться другим
активным WireGuard-подключением: сервер будет переключать endpoint одного peer.

Все команды выполняются из корня проекта. На Client1 нужны исходники проекта
и `wg/Client1.conf`, на Client2 — исходники, `wg/Client2.conf` и тестовый JPG.
Ключи не копируются в Docker-образы: конфиги монтируются только при запуске,
read-only. Настройка DNS из конфига убирается во временной копии внутри контейнера;
исходные файлы сохраняются.

**Client1 — поднять приёмник:**

```bash
docker compose -f compose.receiver.yml up -d --build
docker compose -f compose.receiver.yml logs -f receiver
```

После строки `READY` можно запускать Client2. Приёмник работает постоянно.

**Client2 — отправить пять пар текст + картинка:**

```bash
docker compose -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

Sender ждёт обнаружения receiver до 60 секунд. Для каждой пары ждёт подтверждение
записи текста и картинки, сверяет SHA-256 и размеры изображения. При таймауте
повторяет неподтверждённое сообщение, максимум 3 попытки по 15 секунд.
Повторная доставка того же ID перезаписывает те же файлы.

Успех — пять строк `PASS` и итоговая `SUCCESS: 5 text/image pairs verified`,
код возврата `0`. Ошибка discovery, записи, контрольной суммы или исчерпание
попыток завершают sender с кодом `1`. Команда также останавливает его WG-контейнер.
Повторный запуск создаёт новую сессию и новые имена файлов.

На **Client1** в `./received/` появятся файлы:

```text
<session>-000001.txt   # исходный UTF-8 текст
<session>-000001.png   # полученные пиксели без потерь
<session>-000001.json  # SHA-256, размер, имя PNG и ID
```

Топики:

| Топик | Тип | Назначение |
| --- | --- | --- |
| `/wg_test/text` | `std_msgs/msg/String` | JSON с ID и текстом |
| `/wg_test/image` | `sensor_msgs/msg/Image` | BGR-массив; ID в `header.frame_id` |
| `/wg_test/ack` | `std_msgs/msg/String` | JSON с результатом сохранения и SHA-256 |

## Параметры

Готовый пример — `.env.wg.example`. Можно скопировать его в `.env.wg` и передавать
`--env-file .env.wg` **обоим** стекам:

```bash
cp .env.wg.example .env.wg
docker compose --env-file .env.wg -f compose.receiver.yml up -d --build
docker compose --env-file .env.wg -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

| Переменная | По умолчанию | Значение |
| --- | --- | --- |
| `WG_TEST_ROS_DOMAIN_ID` | `42` | Одинаковый на обеих сторонах |
| `WG_TEST_COUNT` | `5` | Число пар; `0` — непрерывно |
| `WG_TEST_INTERVAL` | `1` | Пауза между подтверждёнными парами, секунды |
| `WG_TEST_TEXT` | `Привет от Client2 через WireGuard!` | Текст |
| `WG_TEST_ACK_TIMEOUT` | `15` | Ожидание подтверждений на попытку, секунды |
| `WG_TEST_DISCOVERY_TIMEOUT` | `60` | Ожидание receiver, секунды |
| `WG_TEST_RETRIES` | `3` | Максимум попыток отправки пары |

Например, непрерывная отправка:

```bash
WG_TEST_COUNT=0 WG_TEST_INTERVAL=2 docker compose -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

Существующие `.env` и `.env.example` с параметрами OpenVPN сохранены.
Новые стеки используют только переменные `WG_TEST_*`.

## Диагностика

На Client1:

```bash
docker compose -f compose.receiver.yml ps
docker compose -f compose.receiver.yml logs wireguard receiver
docker compose -f compose.receiver.yml exec wireguard wg show wg0
docker compose -f compose.receiver.yml exec wireguard ip route get 10.10.0.3
docker compose -f compose.receiver.yml exec wireguard ping -c 3 10.10.0.3
```

На Client2, пока его стек работает:

```bash
docker compose -f compose.sender.yml exec wireguard wg show wg0
docker compose -f compose.sender.yml exec wireguard ip route get 10.10.0.4
docker compose -f compose.sender.yml exec wireguard ping -c 3 10.10.0.4
```

Для длительной диагностики можно сначала запустить только туннель Client2:

```bash
docker compose -f compose.sender.yml up -d --build wireguard
docker compose -f compose.sender.yml exec wireguard wg show wg0
docker compose -f compose.sender.yml exec wireguard ping -c 3 10.10.0.4
docker compose -f compose.sender.yml run --rm sender
docker compose -f compose.sender.yml down
```

`healthy` у WG означает, что интерфейс создан; доступность сервера и второго
клиента этим не подтверждается. В `wg show` ищите свежий `latest handshake`
и рост счётчиков transfer. Есть handshake, но клиенты не видят друг друга —
проверьте IP forwarding, правила FORWARD и изоляцию клиентов на сервере.
Ping может блокироваться отдельно; окончательная проверка — `PASS` от sender.

Для домена `42` и participant index `0..32` DDS использует UDP `17910..17975`
на WG-адресах (discovery и данные). Для другого домена базовый порт:
`7400 + 250 * ROS_DOMAIN_ID + 10`; последний — базовый `+ 65`.
Это внутренние порты туннеля, их не требуется публиковать на Docker-хосте.

Остановка и удаление контейнеров (полученные файлы сохраняются):

```bash
docker compose -f compose.sender.yml down
docker compose -f compose.receiver.yml down
```

## Локальные проверки без WireGuard

При установленном Python с `numpy` и `opencv-python`:

```bash
python3 -m unittest discover -s tests -v
docker compose -f compose.receiver.yml config --quiet
docker compose -f compose.sender.yml config --quiet
```

Тесты проверяют запись именно указанного JPG в PNG с точным совпадением пикселей,
Unicode-текст, повторы, отказ при ошибке записи/искажении файла/неверном ACK,
защиту имён файлов и запрет маршрута DDS через другой интерфейс.
Они не заменяют запуск двух стеков и проверку реального туннеля.

При сборке Docker-образа также автоматически запускается `scripts/check_dds.py`:
он создаёт настоящий ROS 2 узел с генерируемым DDS XML, заменяя только адреса
и интерфейс на loopback. Так сборка выявляет несовместимые параметры Cyclone DDS
ещё до запуска VPN. В рабочем режиме по-прежнему обязателен `wg0`.

Если в старом образе появляется `Transport/#text: 'udp4': undefined value`,
пересоберите образ: допустимое значение UDP/IPv4 в XML — `udp`.

```bash
docker compose -f compose.receiver.yml up -d --build --no-deps receiver
docker compose -f compose.receiver.yml logs --tail 30 receiver
```

На Client2 образ sender также нужно пересобрать обычной командой запуска
с `--build`. Изменения исходников не попадают в уже собранный образ автоматически.

Документация настроек:
[Cyclone DDS — discovery](https://cyclonedds.io/docs/cyclonedds/latest/config/discovery-config.html),
[Cyclone DDS — сетевые интерфейсы](https://cyclonedds.io/docs/cyclonedds/latest/config/network_interfaces.html),
[Cyclone DDS — XML-схема Transport](https://raw.githubusercontent.com/eclipse-cyclonedds/cyclonedds/releases/0.10.x/etc/cyclonedds.xsd),
[WireGuard userspace implementation](https://git.zx2c4.com/wireguard-go/about/).
