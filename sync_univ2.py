# -*- coding: utf-8 -*-#
# -------------------------------------------------------------------------------
# Name:         a 
# Author:       yepeng
# Date:         2021/10/22 2:44 下午
# Description: 同步uniswap v2 pool数据
# -------------------------------------------------------------------------------
import argparse
import json
import logging
import time
from datetime import datetime

import toml
from eth_abi import abi
from pydantic import BaseModel
from pymongo import MongoClient
from web3 import Web3, HTTPProvider
from web3.contract import Contract

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
lg = logging.getLogger(__name__)
parser = argparse.ArgumentParser()

parser.add_argument("--config", "-c", type=str)


class MongoConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str


class Config(BaseModel):
    title: str
    network: str
    dex: str
    pool: str
    node_url: str
    always: bool
    start_block: int
    end_block: int
    block_spacing: int
    interval: int
    mongo: MongoConfig


class SyncUniv2Pool:
    def __init__(self, config_path: str):
        self.conf: Config = self._load_config(config_path)
        self.dbname: str = self.conf.network
        self.coll_action = f"{self.conf.dex}_{self.conf.pool[0:8]}"
        self.coll_pool = f"{self.conf.dex}_pools"
        self._pair_abi = self._read_pair_abi()

        self.db: MongoClient = self._connect_mongo()
        self.w3: Web3 = self._connect_eth_client()
        self._erc20_abi = self._read_erc20_abi()

    @staticmethod
    def _load_config(file_path: str) -> Config:
        try:
            f = toml.load(file_path)
            c = Config.parse_obj(f)
            return c
        except Exception as e:
            logging.error(e)
            exit()

    @staticmethod
    def _read_erc20_abi():
        with open('./source/abi/IERC20.abi', 'r') as f:
            return f.read()

    @staticmethod
    def _read_pair_abi():
        with open('./source/abi/IUniswapV2Pair.abi', 'r') as f:
            return f.read()

    # 加载以太坊客户端
    def _connect_eth_client(self) -> Web3:
        lg.info(f"_connect_eth_client ... ...")
        return Web3(HTTPProvider(endpoint_uri=self.conf.node_url))

    # 获取数据库，根据网络名称命名，如ethereum，这样可支持多链数据同步
    def _connect_mongo(self):
        lg.info(f"_connect_mongo ... ...")
        host = self.conf.mongo.host
        port = self.conf.mongo.port
        username = self.conf.mongo.username
        password = self.conf.mongo.password
        client = MongoClient(host=host, port=port, username=username, password=password)
        return client

    def _create_index(self):
        # event 索引
        lg.info(f"_create_index")

        self.db[self.dbname][self.coll_action].create_index([('action', 1)])
        self.db[self.dbname][self.coll_action].create_index([('ts', 1)])
        self.db[self.dbname][self.coll_action].create_index([('block_number', 1)])
        self.db[self.dbname][self.coll_action].create_index([('maker', 1)])

    # 获取相关地址event
    def _get_logs(self, start_block, end_block):
        try:
            return self.w3.eth.get_logs({
                'fromBlock': start_block,
                'toBlock': end_block,
                'address': self.w3.to_checksum_address(self.conf.pool)})
        except Exception as e:
            lg.info(f"{e}")
            return None

    # 扫描范围区块
    def _scan_event(self, start_block, end_block) -> bool:
        logs = self._get_logs(start_block, end_block)
        if logs is None:
            return False
        buff = []
        for log in logs:
            topic0 = log['topics'][0].hex().lower()
            if topic0 == "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822".lower():
                data = self._parse_swap(log)
                buff.append(data)
                lg.info(f"find event swap")
                continue
            if topic0 == "0x4c209b5fc8ad50758f13e2e1088ba56a560dff690a1c6fef26394f4c03821c4f".lower():
                data = self._parse_mint(log)
                lg.info(f"find event mint")
                buff.append(data)

                continue
            if topic0 == "0xdccd412f0b1252819cb1fd330b93224ca42612892bb3f4f789976e6d81936496".lower():
                data = self._parse_burn(log)
                buff.append(data)
                lg.info(f"find event burn")
                continue
        if not buff:
            return True
        try:
            self.db[self.dbname][self.coll_action].insert_many(buff, ordered=False)
        except Exception as e:
            lg.error(f"insert data failed:{e} -> pass")

        return True

    # 构建erc20 tolen 实例
    def _gen_erc20_instance(self, erc20_address: str) -> Contract:
        contract_address = self.w3.to_checksum_address(erc20_address)
        return self.w3.eth.contract(address=contract_address, abi=self._erc20_abi)

    @staticmethod
    def scal_amount(x, n):
        return x / 10 ** n

    # 解析burn事件-> 移除流动性
    def _parse_burn(self, log):
        data = log.get('data')
        txhash = log.get("transactionHash").hex()
        arg_types = ['uint256', 'uint256']
        (amount0, amount1) = abi.decode(arg_types, data)
        block_number = log['blockNumber']
        block = self.w3.eth.get_block(block_number)
        ts = block.get("timestamp")
        ts_date = datetime.utcfromtimestamp(ts)
        a0 = self.scal_amount(amount0, self.pool_info['t0']['decimal'])  # 得到t0 数量
        a1 = self.scal_amount(amount1, self.pool_info['t1']['decimal'])  # 得到t0 数量
        mint_data = {
            "action": "remove",
            "block_number": block_number,
            "ts": ts,
            "ts_date": ts_date,
            "amount_a": a0,
            "token_a": self.pool_info['t0']['symbol'],
            "amount_b": a1,
            "token_b": self.pool_info['t1']['symbol'],
            "maker": None,
            "txhash": txhash
        }
        return mint_data

    # 解析mint事件-> 添加流动性
    def _parse_mint(self, log):
        data = log.get('data')
        txhash = log.get("transactionHash").hex()
        arg_types = ['uint256', 'uint256']
        (amount0, amount1) = abi.decode(arg_types, data)
        block_number = log['blockNumber']
        block = self.w3.eth.get_block(block_number)
        ts = block.get("timestamp")
        ts_date = datetime.utcfromtimestamp(ts)
        a0 = self.scal_amount(amount0, self.pool_info['t0']['decimal'])  # 得到t0 数量
        a1 = self.scal_amount(amount1, self.pool_info['t1']['decimal'])  # 得到t0 数量
        mint_data = {
            "action": "add",
            "block_number": block_number,
            "ts": ts,
            "ts_date": ts_date,
            "amount_a": a0,
            "token_a": self.pool_info['t0']['symbol'],
            "amount_b": a1,
            "token_b": self.pool_info['t1']['symbol'],
            "maker": None,
            "txhash": txhash
        }
        return mint_data

    # 解析swap事件-> swap
    def _parse_swap(self, log):
        # // Solidity: event Swap(address indexed sender, uint256 amount0In, uint256 amount1In, uint256 amount0Out, uint256 amount1Out, address indexed to)
        data = log.get('data')
        txhash = log.get("transactionHash").hex()
        arg_types = ['uint256', 'uint256', 'uint256', 'uint256']
        (amount0in, amount1in, amount0out, amount1out) = abi.decode(arg_types, data)
        maker = log['topics'][2].hex()
        maker = maker[0:2] + maker[-40:]

        block_number = log['blockNumber']
        block = self.w3.eth.get_block(block_number)
        ts = block.get("timestamp")
        ts_date = datetime.utcfromtimestamp(ts)
        a0 = self.scal_amount(amount0out - amount0in, self.pool_info['t0']['decimal'])  # 得到t0 数量
        a1 = self.scal_amount(amount1out - amount1in, self.pool_info['t1']['decimal'])  # 得到t0 数量

        swap_data = {
            "action": "swap",
            "block_number": block_number,
            "ts": ts,
            "ts_date": ts_date,
            "amount_a": a0,
            "token_a": self.pool_info['t0']['symbol'],
            "amount_b": a1,
            "token_b": self.pool_info['t1']['symbol'],
            "maker": maker,
            "txhash": txhash
        }
        return swap_data

    # 获取远程高度
    def _get_remote_erc20(self, addr: str) -> dict | None:
        try:
            erc20_instance = self._gen_erc20_instance(addr)
            symbol = getattr(erc20_instance.functions, "symbol")().call()
            decimal = getattr(erc20_instance.functions, "decimals")().call()
            total_supply = getattr(erc20_instance.functions, "totalSupply")().call()
            return {
                'address': addr,
                'symbol': symbol,
                'decimal': decimal,
                'total_supply': total_supply / 10 ** decimal
            }
        except Exception as e:
            lg.error(f"_get_remote_erc20:{e}")
            return None

    # 构建pair实例
    def _gen_pair_instance(self, pair_address: str) -> Contract:
        contract_address = self.w3.to_checksum_address(pair_address)
        return self.w3.eth.contract(address=contract_address, abi=self._pair_abi)

    # 获取池子基本信息
    def _fetch_pool(self):
        lg.info(f"_fetch pool info:{self.conf.pool}")
        p = self.db[self.dbname][self.coll_pool].find_one(filter={'pool': self.conf.pool})
        if not p:
            pair_instance = self._gen_pair_instance(self.conf.pool)
            token0 = getattr(pair_instance.functions, "token0")().call()
            token1 = getattr(pair_instance.functions, "token1")().call()
            t0_info = self._get_remote_erc20(token0)
            t1_info = self._get_remote_erc20(token1)
            p = {
                "pool": self.conf.pool,
                "network": self.conf.network,
                "dex": self.conf.dex,
                "t0": t0_info,
                "t1": t1_info,
                "sync_start": self.conf.start_block,
                "sync_last": self.conf.start_block
            }
            self.db[self.dbname][self.coll_pool].insert_one(p)  # 插入pool coll
        else:
            return {
                "pool": p['pool'],
                "network": p['network'],
                "dex": p['dex'],
                "t0": p['t0'],
                "t1": p['t1'],
            }

    # 获取当前高度
    def _get_current_block_height(self) -> int:
        try:
            return self.w3.eth.get_block_number()
        except Exception as e:
            lg.error(f"_get_current_block_height failed:{e}")
            return 0

    def _get_sync_last(self) -> int:
        pool = self.db[self.dbname][self.coll_pool].find_one(filter={'pool': self.conf.pool})
        if pool:
            return pool['sync_last']
        else:
            return 0

    def _set_sync_last(self, height):
        self.db[self.dbname][self.coll_pool].find_one_and_update({"pool": self.conf.pool}, update={
            '$set': {'sync_last': height}
        })
        lg.info(f"_set_sync_last:{height}")

    def _to_sync(self, start: int, end: int):
        size = self.conf.block_spacing
        for i in range(start, end, size):
            next_end = min(i + size - 1, end)
            ok = self._scan_event(i, next_end)
            if not ok:
                return
            self._set_sync_last(next_end)

    def run(self):
        self._create_index()
        self.pool_info = self._fetch_pool()
        lg.info(json.dumps(self.pool_info, indent=4))
        while True:
            x = self._get_sync_last()
            y = self._get_current_block_height()
            z = self.conf.end_block

            if not x or not y:
                lg.error(f"x={x} y={y} sync failed -> continue")
                time.sleep(10)
                continue
            if not self.conf.always and x >= z:
                exit(0)
            if x > y:
                lg.warning(f"x > y,continue")
                time.sleep(10)
                continue
            if x == y:
                time.sleep(10)
                continue
            lg.info(f"x:{x} y:{y}")
            self._to_sync(x + 1, y)
            time.sleep(self.conf.interval)


if __name__ == '__main__':
    lg.info("start to sync uniswap v2,good luck ... ...")
    args = parser.parse_args()
    cpath: str = args.config
    if not cpath:
        lg.error("pleace input config path,eg:'python mian.py -c config.toml' ")
        exit(500)
    lg.info(cpath)
    task = SyncUniv2Pool(cpath)
    task.run()
