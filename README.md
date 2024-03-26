# uniswap v2 池子事件同步器

## 安装启动
```shell
# 建议在单独py 环境下执行脚本，防止冲突
pip install -r requirements.txt

# 配置文件地址替换成你的
python sync_univ2.py -c ./0xdasdasdasdasasdas.toml

# wait... ...

```

## 配置文件格式
```toml
title = "uniswap v2 sync&parse"

#[必选]区块网络，必选，与节点url关
network = "ethereum"
# [必选]dex dex类型，别改
dex = "univ2"

#[必选]uniswap v2 pool 地址
pool = "0x769f539486b31eF310125C44d7F405C6d470cD1f"

# [必选]替换你的服务商节点url，注意与network兼容
node_url = "https://mainnet.infura.io/v3/**********"

#[必选]是否一直运行，如果为true，那么程序将一直跟随最新高度同步数据，直至地球爆炸，如果为false，同步将在end_block处停止
always = true

#[必选]起始点区块
start_block = 19517454
# 结束点区块
end_block = 0

# 区块扫描间隔，100～300即可，根据网络负载，不宜过大
block_spacing = 200

# 预估区块增长时间，根据不同的链，例如ethereum 为10秒
interval = 10

# 数据库配置，数据库需要使用mongodb，其中的参数需要自行配置
[mongo]
host = "localhost"
port = 5008
username = "root"
password = "password"
```
