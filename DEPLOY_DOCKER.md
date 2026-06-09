# Docker 部署说明

本项目当前没有独立前端容器。后端 FastAPI 容器会直接服务仓库内已有的 `html/` 静态产物，并挂载 `deploy/config.docker.yaml` 作为容器内的 `config.yaml`。

## 文件说明

- `Dockerfile`：构建 Python 后端镜像。
- `docker-compose.yml`：启动后端和 MySQL 8.4。
- `docker-compose.dev.yml`：启动开发环境，后端连接宿主机 MySQL，前端使用 Vite dev server。
- `deploy/config.docker.yaml`：Docker 环境配置示例。
- `deploy/config.local-mysql.docker.sample.yaml`：连接宿主机 MySQL 的开发配置模板。
- `requirements.txt`：后端 Python 依赖。

## 启动前配置

先编辑 `deploy/config.docker.yaml`：

- 修改 `jwt.secret_key`
- 修改 `admin.default_password`
- 修改 `ai.api_key`
- 如果需要账号登录，修改 `oauth.client_id`、`oauth.client_secret`、`oauth.redirect_uri`
- 如果修改 compose 中的 MySQL 用户名、密码、库名，也同步修改 `database` 配置。

生产环境建议复制一份私有配置，例如：

```bash
cp deploy/config.docker.yaml config.docker.local.yaml
```

然后把 `docker-compose.yml` 里的挂载路径改为：

```yaml
./config.docker.local.yaml:/app/config.yaml:ro
```

`config.docker.local.yaml` 不应提交到代码库。

可选：创建 `.env` 覆盖 compose 变量：

```env
APP_PORT=8002
BASE_IMAGE=python:3.12-slim
APT_MIRROR=mirrors.ustc.edu.cn
PYPI_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
MYSQL_PORT=3306
MYSQL_DATABASE=asplatform
MYSQL_USER=asplatform
MYSQL_PASSWORD=asplatform_password
MYSQL_ROOT_PASSWORD=root_password
OAUTH_DEV_HOST=oauth.localhost
```

如果构建失败发生在拉取基础镜像 `python:3.12-slim` 或 `mysql:8.4`，这不是 Dockerfile 内部 apt/pip 镜像能解决的，需要在 Docker Desktop 或 Docker daemon 里配置 registry mirror，或者提前手动拉取可访问的镜像后通过 `BASE_IMAGE` 替换。

## 启动

```bash
docker compose up -d --build
```

app 容器启动时会先执行：

```bash
uvicorn main:app --host 0.0.0.0 --port 8002
```

访问：

```text
http://localhost:8002
```

## Release 镜像运行

如果线上只运行 app 容器，MySQL 使用外部数据库或已经单独部署的数据库，可以用 release 镜像方式发布。

发布前先确保前端静态产物已经同步到后端服务目录：

```text
frontend/dist/* -> html/
```

准备一份只在服务器保存的配置文件，例如：

```text
/opt/asplatform/config.yaml
```

其中 `database` 应指向线上 MySQL，例如：

```yaml
database:
  type: mysql
  url: ""
  host: "your-mysql-host"
  port: 3306
  database: "asplatform"
  username: "asplatform"
  password: "your-password"
```

构建 release 镜像：

```bash
docker build \
  --build-arg BASE_IMAGE=python:3.12-slim \
  -t asplatform:release .
```

运行 release 容器：

```bash
docker run -d \
  --name asplatform-app \
  --restart unless-stopped \
  -p 8002:8002 \
  -v /opt/asplatform/config.yaml:/app/config.yaml:ro \
  asplatform:release
```

如果容器需要访问宿主机上的 MySQL，可以把 `database.host` 写成 `host.docker.internal`，并在 Linux 服务器上运行时增加：

```bash
--add-host host.docker.internal:host-gateway
```

完整示例：

```bash
docker run -d \
  --name asplatform-app \
  --restart unless-stopped \
  --add-host host.docker.internal:host-gateway \
  -p 8002:8002 \
  -v /opt/asplatform/config.yaml:/app/config.yaml:ro \
  asplatform:release
```

发布新版本时：

```bash
docker stop asplatform-app
docker rm asplatform-app
docker build -t asplatform:release .
docker run -d --name asplatform-app --restart unless-stopped -p 8002:8002 -v /opt/asplatform/config.yaml:/app/config.yaml:ro asplatform:release
```

## 本地开发模式

如果开发时使用宿主机上的 MySQL，而不是 compose 里的 MySQL，可以使用开发 compose 文件：

```bash
cp deploy/config.local-mysql.docker.sample.yaml deploy/config.local-mysql.docker.yaml
docker compose -f docker-compose.dev.yml up --build
```

这个模式：

- 不启动 MySQL 容器。
- app 容器通过 `host.docker.internal:3306` 连接宿主机 MySQL。
- app 容器会把 `.env` 中的 `OAUTH_DEV_HOST` 映射到宿主机，方便访问本机 hosts 域名。
- app 容器使用 `uvicorn --reload`。
- frontend 容器挂载 `frontend/` 并运行 Vite dev server。
- Vite 的 `/api` 请求会代理到 compose 网络里的 `http://app:8002`。
- 前台运行，方便直接看日志；开发时通常比 `up -d` 更合适。

启动前需要编辑：

```text
deploy/config.local-mysql.docker.yaml
```

这个文件会被 `.gitignore` 忽略，可以写入你的本地数据库密码和 OAuth 密钥。

至少修改：

- `database.database`
- `database.username`
- `database.password`
- `jwt.secret_key`
- 如需账号登录，修改 `oauth.client_id`、`oauth.client_secret`、`oauth.redirect_uri`

如果你的 OAuth 线下服务是通过宿主机 `/etc/hosts` 域名访问的，需要创建或编辑项目根目录 `.env`：

```env
OAUTH_DEV_HOST=你的线下域名
```

然后在 `deploy/config.local-mysql.docker.yaml` 里使用同一个域名：

```yaml
oauth:
  base_url: "http://你的线下域名"
  payment_base_url: "https://www.keyan.asia"
  redirect_uri: "http://localhost:5173/oauth/callback"
  payment_return_url: "http://localhost:5173/payment/return"
  payment_notify_url: "https://your-api-domain.example.com/api/payment/notify"
  products_path: "/oauth/as-platform-product"
  trust_env: false
  purchase_url: ""
  auto_provision_token: false
  user_session_expires_hours: 24
```

这样后端容器访问 `http://你的线下域名` 时，会通过 compose 的 `extra_hosts` 解析到宿主机，同时保留原始 Host。
`trust_env: false` 会让 OAuth 请求不读取系统代理环境变量，避免本机 hosts 域名被代理转走。

访问：

```text
http://localhost:5173
```

`frontend/node_modules` 使用 Docker volume 保存，避免把宿主机的 `node_modules` 混进 Linux 容器。如果你的包源镜像拿不到某些版本，可以只保留后端容器运行，前端继续在宿主机跑 `yarn dev`。

只启动后端容器：

```bash
docker compose -f docker-compose.dev.yml up app --build
```

## 账号登录 OAuth

账号登录通过后端 `/api/oauth/start` 创建外部授权链接，回调到 `/oauth/callback` 后由后端换取外部用户信息并绑定一个内部服务令牌。前端不会保存或提交 `client_secret`。

默认配置示例在：

```text
config.sample.yaml
deploy/config.docker.yaml
deploy/config.local-mysql.docker.sample.yaml
```

上线时需要确认 `oauth.redirect_uri` 与外部 OAuth 平台配置一致，例如：

```yaml
oauth:
  base_url: "https://curyian.com"
  payment_base_url: "https://www.keyan.asia"
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  redirect_uri: "https://your-domain.example.com/oauth/callback"
  payment_return_url: "https://your-domain.example.com/payment/return"
  payment_notify_url: "https://your-api-domain.example.com/api/payment/notify"
  products_path: "/oauth/as-platform-product"
  trust_env: false
  purchase_url: "https://your-domain.example.com/pricing"
  auto_provision_token: false
  user_session_expires_hours: 24
  default_ai_quota: 1000000.0
  default_permissions: "bio,ai"
```

`purchase_url` 用于服务令牌过期时引导用户购买或续费；留空时前端会继续引导用户使用账号登录入口。
`auto_provision_token` 控制 OAuth 登录后是否自动创建内部服务令牌。默认建议为 `false`，这样未购买用户登录后会看到购买提示；内部测试时可以临时改为 `true`。
`user_session_expires_hours` 控制 OAuth 登录成功后，本项目签发的本地用户会话令牌有效期。它只用于购买流程，不等同于服务令牌。
`payment_return_url` 必须与 OAuth 后台配置的支付回跳地址完全一致。
`payment_notify_url` 需要配置在 OAuth 后台，用于支付成功后通知本项目后端 `/api/payment/notify`。
`products_path` 是 OAuth 后台提供的产品展示接口路径，当前项目不再维护本地产品配置。该接口按文档不需要登录态或 OAuth token。

当前支付接入会创建本地 `payment_orders` 订单并跳转到 OAuth 后台返回的 `pay_url`。支付成功后，OAuth 后台应通知 `/api/payment/notify`，本项目会按 `third_order_no` 更新本地订单状态，并根据购买产品额度自动发放服务 token；支付回跳页会轮询 `/api/payment/status/{third_order_no}` 等待状态同步。

未购买用户首次购买走 `/payment/purchase`，使用 OAuth 登录后签发的本地 `user_token` 创建订单；已付费用户升级或加购走 `/payment/upgrade`，使用当前服务 token 创建订单，避免和首次购买认证流程混用。

产品 `slug` 用于标记套餐等级，目前按 `experience < basic < pro` 判断升级关系。支付成功发放 token 时，若购买同等级产品，会从当前同等级 token 的过期时间继续顺延；若购买更高等级产品，则新等级立即生效，token 过期时间从当前时间开始计算，并禁用该用户仍处于 active 状态的低等级旧 token。产品未返回 `duration_days` 时默认按 30 天发放。

## 数据库结构

项目沿用原有的 `Base.metadata.create_all` 建表模式，不引入 Alembic。

OAuth 相关新增结构包括：

```text
external_users
oauth_user_sessions
tokens.external_user_id
payment_orders
payment_order_entitlements
```

如果是全新数据库，后端启动时会通过 `create_all` 创建这些结构。如果是已有数据库，需要手动补齐对应字段、索引和唯一约束。

注意：`tokens.external_user_id` 只是普通整数字段，不加外键。
`payment_order_entitlements` 记录购买时的产品快照、支付通知原文、支付金额、发放的 `tokens.id` 和发放额度。AI 请求实际扣减仍发生在 `tokens.used_quota`，这张表用于回溯某个 token 来自哪笔订单和哪个产品。

如果账号登录时报：

```text
httpx.ConnectError: [Errno -2] Name or service not known
```

通常表示后端容器无法解析或访问 `oauth.base_url` 的域名。优先检查：

- `oauth.base_url` 是否写成完整地址，例如 `https://curyian.com`。
- 当前 Docker 容器是否能访问外网 DNS。
- Docker Desktop 或 Docker daemon 是否需要配置代理、DNS 或镜像网络。
- 本机能打开该域名，不代表容器内一定能解析该域名。

如果你不想用 Docker 跑 app，也可以直接在宿主机运行 Python 后端：

```bash
cp config.sample.yaml config.yaml
```

然后把 `config.yaml` 的数据库改为：

```yaml
database:
  type: mysql
  url: ""
  host: "127.0.0.1"
  port: 3306
  database: "asplatform"
  username: "root"
  password: "your-local-password"
```

再用本地 Python 环境启动后端。

## 查看日志

```bash
docker compose logs -f app
docker compose logs -f mysql
```

## 停止

```bash
docker compose down
```

如需同时删除 MySQL 数据卷：

```bash
docker compose down -v
```

## 注意事项

- `config.yaml` 被 `.gitignore` 忽略，生产环境不要提交真实密钥。
- `deploy/config.local-mysql.docker.yaml` 被 `.gitignore` 忽略，开发时从 `deploy/config.local-mysql.docker.sample.yaml` 复制后自行填写。
- 当前后端保留 `Base.metadata.create_all` 自动建表；已有数据库的字段清理和结构补齐需要手动处理。
- `docker-compose.yml` 不挂载源码，改后端代码后需要重新构建镜像。
- `docker-compose.dev.yml` 会同时启动后端开发容器和 Vite 前端开发容器。
- 前端源码不会被后端容器自动编译；如果后端服务的是 `html/` 静态产物，改 `frontend/src` 后需要重新构建前端产物，或者开发时单独使用 Vite/yarn dev。
- 开发模式从 `http://localhost:5173` 访问，生产/静态模式从后端端口访问。
