FROM nginx:alpine

# 静态文件
COPY 50x.html /usr/share/nginx/html/50x.html
COPY favicon.svg /usr/share/nginx/html/favicon.svg
COPY icons.svg /usr/share/nginx/html/icons.svg
COPY index.html /usr/share/nginx/html/index.html
COPY bigscreen-index-v5.html /usr/share/nginx/html/bigscreen-index-v5.html

# 大屏 React 产物 + 增强脚本
COPY assets/ /usr/share/nginx/html/assets/

# nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf
