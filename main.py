from astrbot.api import logger
from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import aiohttp


async def image_obfus(img_data):
    """破坏图片哈希"""
    from PIL import Image as ImageP
    from io import BytesIO
    import random

    try:
        with BytesIO(img_data) as input_buffer:
            with ImageP.open(input_buffer) as img:
                if img.mode != "RGB":
                    img = img.convert("RGB")

                width, height = img.size
                pixels = img.load()

                points = []
                for _ in range(3):
                    while True:
                        x = random.randint(0, width - 1)
                        y = random.randint(0, height - 1)
                        if (x, y) not in points:
                            points.append((x, y))
                            break

                for x, y in points:
                    r, g, b = pixels[x, y]

                    r_change = random.choice([-1, 1])
                    g_change = random.choice([-1, 1])
                    b_change = random.choice([-1, 1])

                    new_r = max(0, min(255, r + r_change))
                    new_g = max(0, min(255, g + g_change))
                    new_b = max(0, min(255, b + b_change))

                    pixels[x, y] = (new_r, new_g, new_b)

                with BytesIO() as output:
                    img.save(output, format="PNG")
                    return output.getvalue()

    except Exception as e:
        logger.warning(f"破坏图片哈希时发生错误: {str(e)}")
        return img_data


@register(
    "astrbot_plugin_setu",
    "Omnisch",
    "Astrbot 色图插件，支持自定义配置与标签指定",
    "2.0.0",
    "https://github.com/Omnisch/astrbot_plugin_setu",
)
class PluginSetu(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.exclude_ai = self.config.get("exclude_ai")
        self.image_hash_break = self.config.get("image_hash_break")
        self.send_forward = self.config.get("send_forward")
        self.image_size = self.config.get("image_size")
        self.image_info = self.config.get("image_info")

    def parse_tags(self, tags: str) -> list[list[str]]:
        """解析标签字符串"""
        if not tags:
            return []

        result = []
        for group in tags.split("&")[:3]:
            tags = [tag.strip() for tag in group.split(",")[:20]]
            if tags:
                result.append(tags)

        return result

    @filter.command_group("setu")
    def setu(self):
        pass

    async def _get_setu(self, event: AstrMessageEvent, tags: str = None, r18: int = 0):
        tags = self.parse_tags(tags)
        send_forward = self.send_forward

        if self.send_forward:
            if event.get_platform_name() != "aiocqhttp":
                send_forward = False
                logger.info("不支持当前平台，已禁用转发")

        retry_count = 0
        while retry_count < 3:
            try:
                async with aiohttp.ClientSession() as session:
                    data = {
                        "r18": r18,
                        "size": [self.image_size],
                        "tag": tags,
                        "excludeAI": self.exclude_ai,
                    }

                    async with session.post(
                        "https://api.lolicon.app/setu/v2",
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as response:
                        response.raise_for_status()
                        resp = await response.json()

                        if not resp["data"]:
                            yield event.plain_result("未获取到图片")
                            return

                        img_url = resp["data"][0]["urls"][self.image_size]
                        img_title = resp["data"][0]["title"]
                        img_author = resp["data"][0]["author"]
                        img_pid = resp["data"][0]["pid"]
                        img_tags = resp["data"][0]["tags"]

                        try:
                            async with session.get(
                                img_url, timeout=aiohttp.ClientTimeout(total=120)
                            ) as img_response:
                                img_response.raise_for_status()
                                img_data = await img_response.read()

                                if self.image_hash_break:
                                    img_data = await image_obfus(img_data)

                                if self.image_info == "只有图片":
                                    chain = [Image.fromBytes(img_data)]
                                elif self.image_info == "基本信息":
                                    chain = [
                                        Image.fromBytes(img_data),
                                        Plain(
                                            f"标题：{img_title}\n作者：{img_author}\nPID：{img_pid}"
                                        ),
                                    ]
                                else:
                                    chain = [
                                        Image.fromBytes(img_data),
                                        Plain(
                                            f"标题：{img_title}\n作者：{img_author}\nPID：{img_pid}\n标签：{' '.join(f'#{tag}' for tag in (img_tags or []))}"
                                        ),
                                    ]

                                if send_forward:
                                    node = Node(
                                        uin=event.get_self_id(),
                                        name="Setu",
                                        content=chain,
                                    )
                                    yield event.chain_result([node])
                                else:
                                    yield event.chain_result(chain)
                                return

                        except aiohttp.ClientError as e:
                            retry_count += 1
                            logger.warning(
                                f"图片下载失败，正在重试 ({retry_count}/3): {str(e)}"
                            )
                            continue

            except aiohttp.ClientError as e:
                logger.error(f"API 请求错误: {str(e)}")
                yield event.plain_result(f"API 请求错误: {str(e)}")
                return
            except Exception as e:
                logger.error(f"发生未知错误: {str(e)}")
                yield event.plain_result(f"发生未知错误: {str(e)}")
                return

        yield event.plain_result(f"获取图片失败，已重试 {retry_count} 次")

    @setu.command("get")
    async def get(self, event: AstrMessageEvent, tags: str = None):
        """随机色图"""
        async for result in self._get_setu(event, tags, r18=0):
            yield result

    @setu.command("r18")
    async def get_r18(self, event: AstrMessageEvent, tags: str = None):
        """随机 R-18 色图"""
        async for result in self._get_setu(event, tags, r18=1):
            yield result

    @setu.command("help")
    async def help(self, event: AstrMessageEvent):
        """帮助"""
        yield event.plain_result(
            "使用方法：\n"
            "  输入 /setu get 获取一张随机涩图\n"
            "  输入 /setu get <tag> 获取特定标签的涩图\n"
            "  - 使用 , 分隔 OR 条件,使用 & 分隔 AND 条件\n"
            "  - 标签中不得有空格，AND 条件最多 3 组，OR 条件每组最多 20 个"
        )
        return
