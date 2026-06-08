FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 构建时注入后端地址，浏览器端通过 localhost 访问宿主机映射端口
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8010
ENV NEXT_PUBLIC_BACKEND_URL=${NEXT_PUBLIC_BACKEND_URL}

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
