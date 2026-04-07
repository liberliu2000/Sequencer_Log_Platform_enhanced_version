# Solution Console Frontend

这是一个独立的 `Next.js + TypeScript + Tailwind + shadcn 风格组件` 前端，使用方式刻意保持为 Streamlit 式单页导航：

- 左侧导航
- 右侧直接渲染页面
- 无复杂前端路由
- 所有核心动作直连真实 FastAPI 后端

## 本地启动

1. 安装依赖

```bash
npm install
```

2. 配置环境变量

```bash
cp .env.example .env.local
```

设置：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

3. 启动开发环境

```bash
npm run dev
```

4. 生产构建验证

```bash
npm run lint
npm run build
```

## 已实现页面

- 欢迎页
- 登录页
- 注册页
- 用户仪表盘
- 管理员仪表盘
- 解决方案库
- 错误码生成器

## 后端要求

前端默认对接现有 FastAPI 接口：

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users/{id}/status`
- `POST /api/v1/admin/users/{id}/roles`
- `GET /api/v1/solution-repository/config`
- `GET /api/v1/solution-repository/records`
- `POST /api/v1/solution-repository/records`
- `PUT /api/v1/solution-repository/records/{id}`
- `GET /api/v1/solution-reviews`
- `POST /api/v1/solution-reviews`
- `POST /api/v1/solution-reviews/{id}/manual-review`
- `GET /api/v1/module-prefixes`
- `POST /api/v1/error-code/generate`

## Vercel 部署

### 方案一：前后端分开部署

推荐把这个 `frontend/` 作为单独的 Vercel 项目部署，后端继续跑在现在的 FastAPI 服务上。

Vercel 项目设置：

- Root Directory: `frontend`
- Framework Preset: `Next.js`
- Build Command: `npm run build`
- Output Directory: `.next`

环境变量：

```bash
NEXT_PUBLIC_API_BASE_URL=https://your-api-domain.com/api/v1
```

如果前端和后端域名不同，确认 FastAPI 允许该前端域名跨域访问。

### 方案二：分别绑定自定义域名

- 前端：`https://solutions.your-domain.com`
- 后端：`https://api.your-domain.com/api/v1`

前端环境变量：

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.com/api/v1
```

### 方案三：同域反向代理

如果你希望前后端走同一主域名，可以让反向代理把：

- `/` 转给 Next.js
- `/api/v1/*` 转给 FastAPI

这样浏览器端无需额外改代码，只要把 `NEXT_PUBLIC_API_BASE_URL` 设为同域的 `/api/v1` 完整地址即可。

## 初始管理员

默认管理员账号来自后端配置：

- 用户名：`Yanbo`
- 密码：`MGItech2026`

建议生产环境首次登录后立即修改密码。
