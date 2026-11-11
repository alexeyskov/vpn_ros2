# ROS 2 через WireGuard

Тест отправки текста и картинки между двумя клиентами WireGuard:

- Client1 (`10.10.0.4`) принимает сообщения и сохраняет их на диск.
- Client2 (`10.10.0.3`) отправляет сообщения и проверяет подтверждения от Client1.

Для каждого клиента есть свой Docker Compose файл. Их можно запустить на двух
компьютерах или на одном: контейнеры используют отдельные туннели и Docker-сети.

```text
Client2 -> wg0 -> WireGuard-сервер -> wg0 -> Client1
Client2 <- wg0 <- WireGuard-сервер <- wg0 <- Client1 (подтверждение)
```

Внутри работают ROS 2 Jazzy, Python/rclpy и Cyclone DDS. ROS использует только
интерфейс `wg0`. Клиенты находят друг друга по заданным IP, без multicast.
Перед запуском проверяется маршрут до второго клиента. Он должен идти через
`wg0` с правильным исходящим адресом. Публиковать порты контейнеров не нужно.

## Быстрый запуск

Нужен запущенный Docker Engine с Compose v2+ или Docker Desktop
с Linux-контейнерами. Все команды ниже выполняются из корня проекта.

Без дополнительных настроек используются два конфига в `wg/`:

```text
wg/Client1.conf   # 10.10.0.4/32, приёмник
wg/Client2.conf   # 10.10.0.3/32, отправитель
```

На первом компьютере запустите приёмник:

```bash
docker compose -f compose.receiver.yml up -d --build
docker compose -f compose.receiver.yml logs -f receiver
```

Дождитесь строки `READY`. Приёмник будет работать, пока вы его не остановите.

Во втором терминале или на втором компьютере запустите отправитель:

```bash
docker compose -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

По умолчанию он отправит пять пар: текст и картинку
`resources/Canon80D_8_8_12800_printer_14_real.jpg`.

При успешной передаче появятся пять строк `PASS`, затем:

```text
SUCCESS: 5 text/image pairs verified
```

Отправитель завершится с кодом `0`, его WireGuard-контейнер тоже остановится.
Приёмник продолжит работать. Если получатель не найден или передача не прошла
проверку, отправитель завершится с кодом `1`.

На компьютере с Client1 в `received/` появятся файлы:

```text
<session>-000001.txt   # полученный текст, UTF-8
<session>-000001.png   # полученная картинка
<session>-000001.json  # ID, SHA-256, размер картинки и имя PNG
```

У каждого запуска свой ID сессии, поэтому результаты разных запусков сохраняются
отдельно. Повторная отправка сообщения с тем же ID перезаписывает его файлы.

## Как использовать свой конфиг

Скачайте свой конфиг из панели WireGuard и положите его в `wg/`.
Например, если файл находится в загрузках:

```bash
mkdir -p wg
cp ~/Downloads/student.conf ./wg/student.conf
```

Путь к конфигу приёмника задаётся через `WG_LISTENER_CONFIG_PATH`,
отправителя через `WG_SENDER_CONFIG_PATH`. Можно указать относительный путь
от корня проекта или абсолютный путь. Файл должен существовать до запуска.
Конфиги `wg/*.conf` исключены из Git.

Свой IP контейнер берёт из поднятого туннеля. В настройках нужно указать
IP второго студента, чтобы ROS знал, где искать другой узел:

- `WG_SENDER_IP` нужен приёмнику: это WG-адрес отправителя.
- `WG_LISTENER_IP` нужен отправителю: это WG-адрес приёмника.

Допустим, у первого студента в конфиге указан `Address = 10.10.0.7/32`,
а у второго `Address = 10.10.0.8/32`.

Первый студент запускает приёмник:

```bash
WG_LISTENER_CONFIG_PATH=./wg/student.conf WG_SENDER_IP=10.10.0.8 \
  docker compose -f compose.receiver.yml up -d --build --force-recreate
```

Второй студент кладёт свой конфиг в `./wg/student.conf` на своём компьютере
и запускает отправитель:

```bash
WG_SENDER_CONFIG_PATH=./wg/student.conf WG_LISTENER_IP=10.10.0.7 \
  docker compose -f compose.sender.yml up --build --force-recreate --abort-on-container-exit --exit-code-from sender
```

Пути у них совпадают, но каждый использует свой файл. Для двух студентов нужны
два разных клиента WireGuard со своими ключами и IP. Значение `ROS_DOMAIN_ID`
у обоих должно совпадать; по умолчанию это `42`.

Оба пути можно записать в `.env.wg`, в том числе одинаковые:

```dotenv
WG_LISTENER_CONFIG_PATH=./wg/student.conf
WG_SENDER_CONFIG_PATH=./wg/student.conf
WG_LISTENER_IP=10.10.0.7
WG_SENDER_IP=10.10.0.8
```

Каждый студент хранит этот файл у себя и запускает нужный Compose
с `--env-file .env.wg`. Приёмник использует только `WG_LISTENER_CONFIG_PATH`,
а отправитель только `WG_SENDER_CONFIG_PATH`.
После замены конфига пересоздайте контейнеры с `--force-recreate`,
чтобы WireGuard прочитал новый файл.

## Что именно отправляется

OpenCV читает JPG в NumPy-массив `uint8 BGR`. Через `cv_bridge` массив превращается
в `sensor_msgs/msg/Image` с кодировкой `bgr8`. Размер тестовой картинки:
512x512x3, то есть 786432 байта пикселей на сообщение.

По ROS передаются сами пиксели. Получатель сохраняет их в PNG без потерь,
перечитывает файл и возвращает SHA-256. Отправитель сравнивает хеш, размеры
картинки и число байт. Проверяется совпадение пикселей после чтения исходного JPG;
байты файлов JPG и PNG будут разными.

Для текста тоже проверяется SHA-256. Сообщения и подтверждения используют
QoS `RELIABLE`. Отправитель ждёт приёмник до 60 секунд, затем отправляет каждую
пару и ждёт подтверждения. Если подтверждение не пришло за 15 секунд, он повторяет
неподтверждённое сообщение. Всего даётся до трёх попыток на пару.

| Топик | Тип | Содержимое |
| --- | --- | --- |
| `/wg_test/text` | `std_msgs/msg/String` | JSON с ID и текстом |
| `/wg_test/image` | `sensor_msgs/msg/Image` | BGR-массив, ID в `header.frame_id` |
| `/wg_test/ack` | `std_msgs/msg/String` | JSON с результатом записи и SHA-256 |

## Настройки

Пример параметров находится в `.env.wg.example`. Скопируйте его в `.env.wg`,
при необходимости поменяйте пути к конфигам и IP, затем укажите файл при запуске:

```bash
cp .env.wg.example .env.wg
docker compose --env-file .env.wg -f compose.receiver.yml up -d --build
docker compose --env-file .env.wg -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

| Переменная | По умолчанию | Для чего нужна |
| --- | --- | --- |
| `WG_LISTENER_CONFIG_PATH` | `./wg/Client1.conf` | Путь к конфигу приёмника на этом компьютере |
| `WG_SENDER_CONFIG_PATH` | `./wg/Client2.conf` | Путь к конфигу отправителя на этом компьютере |
| `WG_LISTENER_IP` | `10.10.0.4` | WG-адрес приёмника, нужен отправителю |
| `WG_SENDER_IP` | `10.10.0.3` | WG-адрес отправителя, нужен приёмнику |
| `WG_TEST_ROS_DOMAIN_ID` | `42` | Должна совпадать у обоих клиентов |
| `WG_TEST_COUNT` | `5` | Число пар сообщений, `0` для непрерывной отправки |
| `WG_TEST_INTERVAL` | `1` | Пауза между подтверждёнными парами, секунды |
| `WG_TEST_TEXT` | `Привет от Client2 через WireGuard!` | Отправляемый текст |
| `WG_TEST_ACK_TIMEOUT` | `15` | Ожидание подтверждения на одну попытку, секунды |
| `WG_TEST_DISCOVERY_TIMEOUT` | `60` | Ожидание приёмника, секунды |
| `WG_TEST_RETRIES` | `3` | Максимальное число попыток на пару |

Например, чтобы отправлять сообщения постоянно с паузой в две секунды:

```bash
WG_TEST_COUNT=0 WG_TEST_INTERVAL=2 docker compose -f compose.sender.yml up --build --abort-on-container-exit --exit-code-from sender
```

В старых `.env` и `.env.example` остались параметры OpenVPN. Эти Compose-файлы
используют переменные `WG_*`, перечисленные выше.

## Настройки WireGuard

Сервер должен разрешать обмен между WG-адресами студентов, в том числе
UDP-трафик ROS. В примере это `10.10.0.3` и `10.10.0.4`. В клиентском конфиге
`AllowedIPs` должен включать адрес второго клиента; в наших конфигах
указана вся подсеть `10.10.0.0/24`.
Сам сервер из этого проекта не разворачивается.

Контейнеру WireGuard нужны `NET_ADMIN` и `/dev/net/tun` на Linux-хосте
или в VM Docker Desktop. `wg-quick` использует модуль ядра, а если его нет,
пробует `wireguard-go`.

Конфиги монтируются только для чтения и не попадают в Docker-образы.
Строка DNS убирается из временной копии конфига внутри контейнера: Docker
использует свой DNS. Исходные файлы в `wg/` остаются без изменений.

На компьютере с приёмником нужны файлы проекта и его выбранный конфиг.
На компьютере с отправителем также нужен тестовый JPG. Один и тот же клиентский конфиг
не стоит одновременно запускать в другом WireGuard-приложении: сервер начнёт
переключать адрес подключения этого клиента.

## Если сообщения не доходят

В командах ниже указаны IP из стандартного примера. Если используются другие
конфиги, подставьте адреса из них.

Сначала посмотрите логи и состояние туннеля на Client1:

```bash
docker compose -f compose.receiver.yml ps
docker compose -f compose.receiver.yml logs wireguard receiver
docker compose -f compose.receiver.yml exec wireguard wg show wg0
docker compose -f compose.receiver.yml exec wireguard ip route get 10.10.0.3
docker compose -f compose.receiver.yml exec wireguard ping -c 3 10.10.0.3
```

На Client2, пока контейнеры работают:

```bash
docker compose -f compose.sender.yml exec wireguard wg show wg0
docker compose -f compose.sender.yml exec wireguard ip route get 10.10.0.4
docker compose -f compose.sender.yml exec wireguard ping -c 3 10.10.0.4
```

Если отправитель уже завершился, можно поднять только его туннель
и запустить тест отдельно:

```bash
docker compose -f compose.sender.yml up -d --build wireguard
docker compose -f compose.sender.yml exec wireguard wg show wg0
docker compose -f compose.sender.yml exec wireguard ping -c 3 10.10.0.4
docker compose -f compose.sender.yml run --rm sender
docker compose -f compose.sender.yml down
```

Статус `healthy` означает, что интерфейс WireGuard создан. Он ещё не говорит
о том, что сервер доступен. В `wg show` проверьте `latest handshake`
и счётчики принятых и отправленных байт.

Если handshake есть у обоих клиентов, проверьте IP forwarding, правила
FORWARD и изоляцию клиентов на сервере. Ping может блокироваться отдельно;
успешную передачу текста и картинки подтверждают строки `PASS` у отправителя.

### Подсеть в wg-easy

После смены CIDR в панели проверьте адрес работающего серверного `wg0`.
В этом проекте была такая проблема: клиенты и сохранённая конфигурация
использовали `10.10.0.0/24`, но на серверном интерфейсе оставался адрес
`10.8.0.1/24`. Поэтому пакеты к клиентам уходили через `eth0`.

Если wg-easy запущен через Docker, выполните на сервере:

```bash
docker exec wg-easy ip -4 address show dev wg0
docker exec wg-easy ip -4 route get 10.10.0.3
docker exec wg-easy ip -4 route get 10.10.0.4
docker exec wg-easy sh -c "grep -E '^[[:space:]]*Address[[:space:]]*=' /etc/wireguard/wg0.conf"
```

Здесь предполагается, что контейнер называется `wg-easy`. Для нашей схемы
на сервере нужен адрес `10.10.0.1/24`, а маршруты к обоим клиентам должны идти
через `wg0`. После исправления активного адреса и NAT тест из пяти пар сообщений
прошёл с совпадением всех SHA-256. В сохранённой конфигурации уже записаны
правильная подсеть и правила NAT.

### Порты ROS

С доменом `42` и participant index `0..32` используются UDP-порты `17910..17975`
на WG-адресах. Для другого домена первый порт считается так:
`7400 + 250 * ROS_DOMAIN_ID + 10`, последний равен первому `+ 65`.
Это порты внутри туннеля, публиковать их на Docker-хосте не нужно.

### Ошибка Transport в старом образе

Если в логах появляется `Transport/#text: 'udp4': undefined value`,
пересоберите образ. Для UDP/IPv4 в XML нужен `Transport=udp`.

```bash
docker compose -f compose.receiver.yml up -d --build --no-deps receiver
docker compose -f compose.receiver.yml logs --tail 30 receiver
```

Образ отправителя тоже пересоберите командой запуска с `--build`.

## Остановка

```bash
docker compose -f compose.sender.yml down
docker compose -f compose.receiver.yml down
```

Полученные файлы останутся в `received/`.

## Проверки без VPN

Для локальных тестов нужен Python с `numpy` и `opencv-python`:

```bash
python3 -m unittest discover -s tests -v
docker compose -f compose.receiver.yml config --quiet
docker compose -f compose.sender.yml config --quiet
```

Тесты проверяют запись картинки без изменения пикселей, Unicode-текст,
повторную доставку, ошибки записи и неверные подтверждения. Также проверяются
имена файлов и маршрут через `wg0`.

При сборке образа запускается `scripts/check_dds.py`. Он создаёт ROS 2 узел
с теми же настройками Cyclone DDS, но на loopback, чтобы поймать ошибки XML
до запуска туннеля. Передачу через настоящий VPN нужно проверять запуском
обоих клиентов.

## Документация

- [Cyclone DDS: discovery](https://cyclonedds.io/docs/cyclonedds/latest/config/discovery-config.html)
- [Cyclone DDS: сетевые интерфейсы](https://cyclonedds.io/docs/cyclonedds/latest/config/network_interfaces.html)
- [Cyclone DDS: XML-схема](https://raw.githubusercontent.com/eclipse-cyclonedds/cyclonedds/releases/0.10.x/etc/cyclonedds.xsd)
- [wireguard-go](https://git.zx2c4.com/wireguard-go/about/)
