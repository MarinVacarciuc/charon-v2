> **ARCHIVED 2026-09-02. Superseded by `docs/BUILD_PLAN.md`.**
>
> Kept deliberately, not deleted: this is the first-iteration design, and the
> differences between it and the current plan are the iteration story itself (P6).
>
> What changed and why:
> * It was written on 18.07, one day **before** `DEMO_ARCHITECTURE_2026-07-19.md`,
>   so it predates the decision that the deliverable is an edited video rather than
>   a live performance. Several of its priorities were tuned for the wrong target.
> * Its Arduino design put the Uno on USB serial into the Mac, with the brain
>   sending `"HB\n"`. The gate is in the yard and the Mac is in the house, so the
>   demo beat could not actually be filmed that way. The Uno now stands alone at
>   the gate on a heartbeat GPIO wire from `gate-in`.
> * Its Uno behaviour was a latching alarm on approach. It is now a green
>   "pass" light: the point of the beat is that the perimeter keeps working.
> * It did not include the camera-off-by-default node behaviour, which is the
>   LO4 privacy and energy story.
>
> What survived unchanged, because it was right: FastAPI + asyncio + SQLite(WAL)
> + SSE, one task per node under a supervisor, the unconditional-assignment rule
> for `except` blocks, IPv4-explicit mDNS resolution, and config-as-data.

# Charon/Cerberus — Ground-Up Server Rebuild

> Рабочий репозиторий: **`~/IdeaProjects/charon`** (git), НЕ текущий cwd (OneDrive/IoT).
> Charon намеренно вне OneDrive из-за проблемы sync/clobber. Все правки — там.
> Общение с пользователем на русском; код, комментарии, git-артефакты — на английском.
> **Никакой Claude/AI-атрибуции в коммитах.**

## Context — зачем это

Старый «мозг» (`~/charon-spikes/process_server.py`, ~1015 строк) — один монолитный
stdlib-`ThreadingHTTPServer` + сырые потоки + один глобальный lock + плоский JSON-на-диск.
Он накопил повторяющиеся классы багов из-за реактивного роста (см. REBUILD_PROMPT §0.6):
поток-убийца из-за `except`, читающего необъявленную переменную (4 из 6 камер молча умерли);
5-секундный mDNS/IPv6-сталл на каждый опрос; глобальный хардкод поворота кадра на 180°;
«biggest face wins» без учёта tailgating; in-memory флаги режима, молча сбрасываемые на рестарте.
Цель — **осознанная пересборка серверной части**, не очередной патч. Железо и прошивка узлов
зафиксированы и проверены (REBUILD_PROMPT §0.2), их НЕ трогаем архитектурно.

Дедлайн живого демо + отчёта: **04.10.2026** (BTEC Unit 21). P5 требует рабочий Arduino Uno +
ультразвук в минимальном демо; P6 требует видимую историю итераций (теги/CHANGELOG с первого дня).

## Зафиксированные архитектурные решения (делегированы пользователем)

1. **Один «мозг», остаётся на Mac.** Не телефон, не два мозга. Все ассеты распознавания
   (YuNet+SFace, порог 0.45) уже проверены именно здесь; дублирование вычислений вернуло бы
   тот самый «слишком много непроверенной поверхности», от которого уходим. Идея телефона-дублёра
   уже описана в `THREAT_MODEL.md` B3 как *design intent* — оставляем её честно
   задокументированным будущим (как TLS, node-attestation), а не строим сейчас.
2. **Сервер: Python, но FastAPI + asyncio.** Одна asyncio-таска на узел, **SSE-push** в админку
   вместо старого polling ~3-4 Гц. Не смена языка (переинтеграция OpenCV-моделей = время без пользы),
   а смена структуры — именно структура была источником багов §0.6.
3. **Хранилище: SQLite** (WAL) вместо плоского JSON-на-персону + текстового audit.log.
   Транзакции, один writer, снятие риска порчи при конкурентной записи.
4. **Arduino Uno — обязателен (P5, тьютор НЕ одобрял отказ).** Роль: независимый физический
   fail-safe watchdog, НЕ второй мозг распознавания (голый Uno, без камеры/WiFi, только USB-serial).
   Механизм — см. раздел «Uno» ниже.

### ⚠ Расхождение для отчёта (флаг пользователю, не блокер)
Доки `Charon_Concept_Design_v0.2…v0.6` **исключают** Uno (замена ультразвуком на ESP32-S3
«с одобрением тьютора, согласуется с Mohamed Hajji»). REBUILD_PROMPT снова делает Uno обязательным.
Пользователь подтвердил: одобрения не было → **бриф всё ещё требует Uno**. Концепция «Heracles»
(Uno-как-watchdog), на которую ссылается REBUILD_PROMPT §5, **нигде в репозитории не задокументирована** —
только одна фраза-указатель. При написании отчёта это надо подать честно как эволюцию решения,
а не как готовый ранее дизайн.

## Верифицированное состояние репозитория (проверено эмпирически)

- `server/` **уже в git**: `server/README.md` + `server/.env.example` описывают заброшенную
  Termux/S10-идею. → Каталог оставляем (правильное имя), **контент переписываем** в Phase 2.
- `.gitignore`: `*.npy /*.embeddings /*.dat` глобальны (ловят эмбеддинги-файлы), НО `.db` не покрыт;
  `*.onnx` и `staff/` привязаны только к `prototype/`. → Нужно добавить `server/data/*.db*`
  и `server/*.onnx` (если модели будут копироваться) ДО первого enrolment. GDPR Art. 9.
- Python: только системный **3.9.6**, Homebrew-питона нет. FastAPI работает на 3.9; для чистого
  `asyncio.TaskGroup` в супервизоре узлов желателен `brew install python@3.12` (низкий риск,
  не блокер — есть 3.9-совместимый ручной супервизор).
- venv `~/charon-spikes/venv`: только `numpy 2.0.2`, `opencv-contrib-python 5.0.0.93`.
  → Доставить: `fastapi uvicorn[standard] aiosqlite aiohttp pyserial pydantic-settings python-multipart`.
- Прошивка (`firmware/charon_node/`, `flash_node.sh`, `ota_node.sh`) **untracked** — закоммитить
  как базовую точку Phase 1. `prototype/*` закоммичен, но расходится с `~/charon-spikes/`.
- Uno сейчас НЕ подключён (нет `/dev/cu.usb*`); git-тегов нет.

## Целевая структура (`~/IdeaProjects/charon/server/`)

```
server/
  app/
    main.py            # FastAPI factory; startup/shutdown: DB, node pollers, Uno-thread
    config.py          # pydantic-settings ← server/.env
    core/              # logging.py, security.py (Phase 6 admin auth — A7 ещё "planned")
    db/
      schema.sql       # DDL — единственный источник истины (раздел ниже)
      migrations/      # 001_init.sql, 002_… — по файлу на реальное изменение = trail для P6
      database.py      # aiosqlite (WAL) + прогон миграций
      repositories/    # people, embeddings, grants, audit, nodes, config_kv
    nodes/
      registry.py      # NodeConfig, seed из MAC-таблицы §0.2
      resolver.py      # IPv4-explicit .local resolve + TTL-кэш (см. ниже)
      poller.py        # NodePoller: одна asyncio-таска/узел + супервизор
      state.py         # in-memory live-состояние узла (кадр, сенсоры, health)
    recognition/
      engine.py        # YuNet+SFace — порт detect()/embed()/recognise()
      policy.py        # policy_ok / perm_zones / zone_allowed — порт
      gate_logic.py    # direction-by-lane, SENSOR-режим, multi-face passage commit
      zone_logic.py    # per-zone multi-face update + throttled unknown-alert
    alerts/            # dispatcher.py (DB-backed), telegram.py
    uno/               # watchdog.py (heartbeat-thread ← pyserial), protocol.py ("HB\n" spec)
    push/              # hub.py (SSE broadcast, asyncio.Queue/клиент), events.py (pydantic-схемы)
    api/               # routes_nodes/people/gate/admin/events(SSE), deps.py
  static/              # admin/ gate/ board/ — plain HTML+JS, без сборки (стиль старой admin.html)
  tests/
  data/                # gitignored — charon.db здесь
  requirements.txt
  .env.example         # переписать (заменить Termux)
  README.md            # переписать
  CHANGELOG.md         # чекпоинты фаз, теги
```
Модуль называем `push/`, а не `ws/` — реально это SSE (см. решение ниже), имя должно
соответствовать содержимому.

## SQLite-схема (ключевое; полный DDL — в schema.sql на этапе реализации)

Открываем соединение один раз: `PRAGMA journal_mode=WAL; foreign_keys=ON; busy_timeout=5000`.
Один app-level `asyncio.Lock` вокруг мутаций (переносим дисциплину старого глобального lock —
он НЕ был источником багов; источником была форма except). WAL даёт конкурентные чтения админки.

Таблицы:
- **`roles`, `zones`, `role_zone_defaults`** — роли/зоны как данные, не хардкод Python-dict; seed
  переносит старую карту (`process_server.py:118`): GUARD/WORKER→Reception,Warehouse,Workshop;
  VISITOR→Reception; ADMIN→все 4; IT→Reception,Server room. Админ-редактируемо без правки кода.
- **`people`** — name(uniq), role_id, telegram_chat_id, hours_from/to, valid_until, access_until
  (JIT-продление часов), max_hours, status(active/suspended), is_dispatcher, presence(in/out),
  session_token, entry_time, at_zone_id, created/updated_at.
- **`person_zone_overrides`** — наличие строк ⇒ полностью переопределяют роль-дефолт (семантика
  старого `perm_zones()`).
- **`zone_grants`** — JIT с независимым `expires_at` на зону, granted_by, revoked_at; частичный
  uniq-индекс на активные (person+zone). Переносим проверенную идею `zgrants()`.
- **`face_embeddings`** — BLOB (128×float32=512 байт, `ndarray.tobytes()`), dim, model_version
  (`sface-2021dec` — защита от смешивания эмбеддингов разных моделей), source(live/photo/migrated),
  много сэмплов на человека. Загрузка в память-кэш на старте.
- **`audit_log`** — структурный: ts, actor, event_type, severity(info/alert), node_id, person_id,
  zone_id, message(human), details_json. `SELECT ts,message ORDER BY ts` воспроизводит старый
  текстовый лог для отчёта.
- **`nodes`** — id, label, role(gate-in/gate-out/zone), zone_id, hostname, mac_address,
  **rotation_deg** (0/90/180/270 — ПЕР-УЗЕЛ, чинит глобальный хардкод §0.6.9), wake_cm/pass_cm
  (читаемый КЭШ порогов; авторитет — NVS на ESP32), thresholds_synced_at, last_seen_ts, online.
  Seed из MAC-таблицы REBUILD_PROMPT §0.2 (6 узлов).
- **`config_kv`** — персистентные флаги (`sensor_mode`, `voice_live`). **Чинит §0.6.6**: режим
  строгости больше не сбрасывается молча на рестарте.

## Async-опрос узлов (критический анти-баг)

Контракт узла (из `charon_node.ino`): `GET http://<node>.local/shot.jpg` → JPEG + заголовки
`X-Passage, X-Dist-Cm, X-Near-Cm, X-Near, X-Node`. Также `/passage` (JSON), `/threshold` (GET
`cm=`/`wake=`, NVS-persist), `/led` (`state=green|red`).

**Домовое правило (чинит §0.6.3):** любое имя, которое читает `except`, присваивается
безусловно ДО любого fallible-вызова — никогда только внутри `try`. Разделяем на два `try`:
«сеть упала» (→ `mark_offline`, `resolver.forget`, `continue` — никогда не проваливаемся в
обработку с полу-собранными данными) и «обработка кадра упала» (→ log, состояние остаётся
last-known-good; баг обработки НЕ переводит живой узел в OFFLINE).

**Супервизор** делает «молча-мёртвый навсегда» структурно невозможным: обёртка `supervise(node)`
ловит любое исключение из `poll_node`, пишет alert в audit, спит 2с, перезапускает. На 3.11+ —
`asyncio.TaskGroup`; на 3.9 — ручной `create_task` + супервизор-цикл.

**IPv4-explicit DNS (чинит §0.6.1, 5.002с→0.010с):**
`await loop.getaddrinfo(host, None, family=socket.AF_INET, ...)` + TTL-кэш 60с. `getaddrinfo`
уже уходит в default executor — ручной поток не нужен, `family=AF_INET` и есть вся починка.
Один общий `aiohttp.ClientSession` на все узлы; коннект по литеральному IP (резолвер aiohttp
не запускается вовсе).

## Multi-face (чинит §0.6.4, 0.6.5)

**Zone-камеры** — старый `zone_worker()` уже прав концептуально: перебирает КАЖДОЕ лицо,
обновляет `at_zone` каждому распознанному, один throttled-alert (15с cooldown) на любое
нераспознанное лицо. Переносим форму почти без изменений (async + DB-backed).

**Gate-камеры** — идём дальше старого «biggest face wins», реализуем cross-check
«camera-face-count vs token-count» (ранее scoped-out как «слишком сложно»). В `gate_logic.py`
на КАЖДОМ sensor-confirmed passage: распознать ВСЕ лица (не только `bi`); разбить на
identified+ok / identified+denied / unidentified; каждому ok — свой gate_event (свой presence-flip,
токен, Telegram); каждому denied — своё отклонение; если `face_count>1` — «possible tailgating»
alert, обогащённый именами (`"2 faces: Marin (granted), 1 unresolved"`); один gate_unknown на
passage, если остались нераспознанные. Camera-only fallback (`SENSOR` off) — старое поведение
по «headline»-лицу, но персистентно через `config_kv` и **видимо помечено как degraded** в
админке (§0.6.6/0.6.7), никогда не молчаливый дефолт после рестарта.

## Push: **SSE, не WebSocket** (команды админа — обычный REST)

Обоснование: авто-reconnect у `EventSource` бесплатный (WS reconnect пишешь/тестишь сам — на
живом 15-мин демо это худший режим отказа); действия админа естественно request/response и
совпадают со старым проверенным паттерном (`fetch('/gate?...')`); видео-тайлы идут отдельно
через `/frame.jpg?node=`; объём событий низкий. Эндпоинт `GET /events`,
`StreamingResponse(media_type="text/event-stream")`, `asyncio.Queue` на клиента, broadcast-hub.
События: `node_status`, `gate`, `alert`, `presence`, `heartbeat` (~15с keepalive). WS — явно
отложенный Phase 6+ вариант, если появится реальная низколатентная двунаправленная нужда.

## Uno — независимый физический watchdog

**Провод:** голый Uno по USB-serial прямо в Mac (та же машина, что и мозг). Свой запасной
RCWL-1601 на два цифровых пина Uno.
**Протокол:** мозг шлёт `"HB\n"` каждые 1000мс, 9600 бод. Uno: `readStringUntil('\n')`, при
точном `HB` → `lastHeartbeat=millis()`. Human-debuggable (видно в Serial Monitor — артефакт для
демо/отчёта: запись экрана + `kill`). Чексумма не нужна (битый = пропущенный, консервативно).
**Таймаут:** 3 подряд пропущенных интервала (~3–3.5с, тот же debounce-паттерн, что у ультразвука)
до «brain offline» — терпит один потерянный байт, укладывается в «пару секунд» для демо.
**Поведение Uno:** «brain offline» → заметный LED (авто-снимается при возврате heartbeat). Пока
armed — опрашивать свой RCWL-1601; при приближении — **защёлкнуть постоянный звуковой alarm**,
который НЕ снимается автоматически при возврате heartbeat, только физический reset (флап мозга
не доказывает, что никто не прошёл во время сбоя). LED и alarm — два независимых состояния.
**Сторона мозга (не стать новой SPOF):** `Serial.write()` блокирующий → выделенный ФОНОВЫЙ
OS-поток (не asyncio-таска), цикл `write("HB\n"); sleep(1.0)`, полностью развязан с event loop.
«Uno не подключён» — graceful: поток переоткрывает порт каждые ~5с, лог-warning, НЕ мешает
остальному мозгу. Дискавери: `serial.tools.list_ports`, VID/PID (Uno=2341, CH340-клон=1a86) +
override `UNO_SERIAL_PORT` в `.env` (снимает неоднозначность, если ESP32 воткнут для прошивки).
Скетч: новый `firmware/uno_watchdog/uno_watchdog.ino`.

## Порядок сборки + версионные чекпоинты (P6)

`server/CHANGELOG.md`, секция на чекпоинт, каждый закрыт реальным `git tag` вживую (не задним числом).

- **Phase 1 — verify firmware as-is** (без редизайна). Закоммитить untracked-прошивку как базу.
  Проверить: 6 плат шьются документированным FQBN/pin-map; `/shot.jpg` + заголовки; mDNS; OTA
  после **ротации утёкшего пароля** `CharonGBS2026`. Физически подписать платы по MAC. Tag `v1-firmware-verified`.
- **Phase 2 — скелет мозга + БД + один узел end-to-end.** FastAPI-скелет, схема+миграции, seed
  реестра, один узел (`gate-in`) через полный async-конвейер, `/frame.jpg?node=gate-in`, рабочий
  `/events` SSE — без распознавания. Переписать `server/README.md` + `.env.example`. Добавить
  `server/data/*.db*` в `.gitignore`. Tag `v2-brain-skeleton`.
- **Phase 3 — все 6 узлов + распознавание + multi-face.** Суб-теги (P6): `v3.1-recognition-engine`,
  `v3.2-gate-logic`, `v3.3-zone-logic`, `v3.4-jit-grants`.
- **Phase 4 — админ-UI.** Сначала информационная архитектура на бумаге (в прошлый раз было
  реактивно). SSE-дашборд, gate-терминал, on-site board, видео-тайл-грид зон, settings с
  человекочитаемым описанием каждого тумблера (именованная жалоба — не регрессировать). Tag `v4-admin-ui`.
- **Phase 5 — Uno watchdog.** Heartbeat-поток + скетч; бенч «kill -9 мозга → alarm за пару секунд»,
  замерить реальную латентность по нескольким прогонам (дом. стиль — реальные числа). Tag `v5-uno-watchdog`.
- **Phase 6 — hardening по threat-model.** Пересмотреть `THREAT_MODEL.md`: часть «planned» станет
  «implemented» (config_kv закрывает B2/§0.6.6; структурный audit_log — часть C3); admin auth (A7);
  TLS если успеваем (C1). Честный split built/designed/limitation заново. Tag `v6-hardening`,
  затем `v6-demo-ready` накануне 04.10.2026.

## Verification (как проверять на каждом этапе)

- **Firmware:** `curl -i http://gate-in.local/shot.jpg` → заголовки `X-Passage/X-Dist-Cm/...`;
  `curl http://gate-in.local/passage` → JSON. Убедиться эмпирически, а не декларативно.
- **Мозг Phase 2:** запустить uvicorn, `curl http://127.0.0.1:PORT/frame.jpg?node=gate-in` вернёт
  JPEG; `curl -N http://127.0.0.1:PORT/events` покажет живой SSE-поток с `node_status`.
- **Anti-bug сценарии (§0.6):** вырубить один узел (отключить питание) → его таска OFFLINE, alert
  в audit, ОСТАЛЬНЫЕ 5 продолжают (изоляция сбоя). Рестарт мозга → `sensor_mode` из `config_kv`
  сохранён (не сброшен). Замерить `getaddrinfo(AF_INET)` vs дефолт (должно быть ~0.01с).
- **Multi-face:** два человека через входной сенсор, одно распознаваемое лицо → alert + отдельный
  исход распознанного. Зона: два известных + один чужой → оба обновления зоны + ровно один alert.
- **Uno:** `kill` процесса мозга на сцене → независимый alarm за пару секунд без софта на Uno;
  записать латентность.

## Открытые вопросы / решить по ходу
- `brew install python@3.12` — ставить перед Phase 2? (желательно, не блокер).
- Снапшот текущего `~/charon-spikes/` в `prototype-final/` одним коммитом как честное «before» (P6)?
- Ротация утёкших секретов (OTA-пароль, ElevenLabs-ключ, TG-токен) — до опоры на них.
