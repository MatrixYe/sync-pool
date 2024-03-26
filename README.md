# uniswap v2 池子事件同步器
> 暂时只支持uniswap v2 pool 数据同步
## 安装启动
同步数据存储在mongodb数据库中，如果在本地部署，请使用docker创建一个单独的mongo容器并将数据挂载到本地
```shell
docker volume create dquant-mongo
docker network create dquant
docker run -itd -p 5008:27017 --name dquant-mongo --network dquant -e MONGO_INITDB_ROOT_USERNAME=root -e MONGO_INITDB_ROOT_PASSWORD=password -v dquant-mongo:/data/db mongo --wiredTigerCacheSizeGB 1.0

```
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

#[必选]是否一直运行，如果为true，那么程序将一直跟随最新高度同步数据，如果为false，同步将在end_block处停止
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

可以同时创造多个配置文件，多进程同步多个pool的数据。建议配置文件与pool同名或关联。

# 数据格式
```json
{
  "_id": {
    "$oid": "66028749d7310e0e56d2dc15"
  },
  
  "action": "remove",
  "block_number": 19407918,
  "ts": 1710112619,
  "ts_date": {
    "$date": "2024-03-10T23:16:59.000Z"
  },
  "amount_a": 899.5854881971859,
  "token_a": "GPU",
  "amount_b": 0.33476863090498526,
  "token_b": "WETH",
  "maker": "unknown",
  "txhash": "0x84165b4bcb12627787d0aad96fb78dc1e381379dafacb3330c7139fd498c8b81"
}
```

- action 动作，swap交换，add 添加流动性，remove移除流动性
- block_number 区块高度
- ts 时间戳
- ts_date 日期
- amount_a 代币a数量
- token_a 代币a名称
- amount_b 代币a数量
- token_b 代币a名称
- maker 交易者，部分找不到
- txhash 交易哈希