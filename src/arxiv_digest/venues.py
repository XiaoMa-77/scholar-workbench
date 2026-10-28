"""顶刊顶会清单与匹配：AI / 机器学习 / 计算机视觉 / NLP / 机器人方向。

"仅顶刊顶会"过滤依据。清单按归一化名称精确匹配 + 子串包含两层判定，
覆盖综合大刊、AI/ML/CV/NLP 核心期刊与会议、机器人核心期刊与会议。
不同数据库对同一会议写法不一（如 "ICLR" 与 "International Conference
on Learning Representations"），子串层用于兜住全称/简写差异。
"""

import re

# 归一化后全等命中的简写与短名
_EXACT = {
    # 综合顶刊
    "nature", "science", "pnas",
    # AI / ML 期刊
    "artificial intelligence", "pattern recognition", "neural networks",
    "transactions on machine learning research", "proceedings of the ieee",
    # 机器人期刊
    "autonomous robots", "soft robotics",
    # 会议简写（S2 venue 常用简写，OpenAlex 常用全称，两层互为补充）
    "neurips", "icml", "iclr", "cvpr", "iccv", "eccv", "aaai", "ijcai",
    "acl", "emnlp", "icra", "iros", "corl", "rss", "ijrr",
}

# 子串包含命中的全称模式（与 _EXACT 中的简写一一呼应），匹配时同样做归一化
_CONTAINS_RAW = [
    # Nature / Science 系列
    "nature machine intelligence", "nature robotics", "science robotics",
    "science advances", "national academy of sciences",
    # AI / ML / CV / NLP 期刊与会议
    "pattern analysis and machine intelligence",                  # IEEE TPAMI
    "international journal of computer vision",                   # IJCV
    "journal of machine learning research",                       # JMLR
    "neural networks and learning systems",                       # IEEE TNNLS
    "neural information processing systems",                      # NeurIPS
    "international conference on machine learning",               # ICML
    "learning representations",                                   # ICLR
    "computer vision and pattern recognition",                    # CVPR
    "international conference on computer vision",                # ICCV
    "european conference on computer vision",                     # ECCV
    "advancement of artificial intelligence",                     # AAAI
    "international joint conference on artificial intelligence",  # IJCAI
    "association for computational linguistics",                  # ACL
    "empirical methods in natural language processing",           # EMNLP
    # 机器人期刊与会议
    "ieee transactions on robotics",                              # T-RO
    "international journal of robotics research",                 # IJRR
    "robotics and automation letters",                            # RA-L
    "robotics and computer-integrated manufacturing",             # RCIM
    "international conference on robotics and automation",        # ICRA
    "intelligent robots and systems",                             # IROS
    "conference on robot learning",                               # CoRL
    "robotics science and systems",                               # RSS 全称
]


def normalize_venue(name: str) -> str:
    """小写、去掉标点、压缩空白，便于跨数据库比对。"""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (name or "").lower())).strip()


# 模式与 venue 走同一套归一化（连字符/冒号等差异不影响匹配）
_CONTAINS = [normalize_venue(pattern) for pattern in _CONTAINS_RAW]


def is_top_venue(name: str) -> bool:
    """判断 venue 是否属于清单内的顶刊/顶会。"""
    normalized = normalize_venue(name)
    if not normalized:
        return False
    if normalized in _EXACT:
        return True
    return any(pattern in normalized for pattern in _CONTAINS)


def top_venue_summary() -> str:
    """给前端提示用的一句话清单。"""
    return (
        "综合：Nature/Science/PNAS；AI·ML：TPAMI、IJCV、JMLR、AIJ、TMLR、"
        "NeurIPS、ICML、ICLR、AAAI、IJCAI；CV：CVPR、ICCV、ECCV；"
        "NLP：ACL、EMNLP；机器人：T-RO、IJRR、RA-L、Science Robotics、"
        "Nature Robotics、ICRA、IROS、CoRL、RSS"
    )
