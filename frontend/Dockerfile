# ---- 前端多阶段构建 ----
FROM node:20-alpine AS build
WORKDIR /app
# 使用阿里云 npm 源加速
RUN npm config set registry https://registry.npmmirror.com
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
