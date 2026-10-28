"""测试共享的内嵌 Atom XML fixture 与配套关键词。"""

# 三篇假论文的 Atom 响应，字段与真实 arXiv API 一致（id/title/summary/author/
# published/category/primary_category），完全离线可用。
ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <link href="http://arxiv.org/api/query" rel="self" type="application/atom+xml"/>
  <title type="html">ArXiv Query: search_query=cat:cs.CV</title>
  <id>http://arxiv.org/api/fixture</id>
  <updated>2026-10-24T00:00:00Z</updated>
  <entry>
    <id>http://arxiv.org/abs/2610.10001v1</id>
    <updated>2026-10-23T18:00:00Z</updated>
    <published>2026-10-23T18:00:00Z</published>
    <title>Vision-Language Diffusion Models
      for 3D Scene Understanding</title>
    <summary>We propose a diffusion framework that couples vision-language
      pretraining with 3D scene understanding.</summary>
    <author><name>Alice Chen</name></author>
    <author><name>Bob Wang</name></author>
    <author><name>Carol Li</name></author>
    <author><name>David Zhang</name></author>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
      term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2610.10001v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2610.10001v1"
      rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2610.10002v1</id>
    <updated>2026-10-22T10:00:00Z</updated>
    <published>2026-10-22T10:00:00Z</published>
    <title>A Survey of Low-Resource Machine Translation</title>
    <summary>We survey recent progress in low-resource translation,
      covering data augmentation and transfer learning methods.</summary>
    <author><name>Eve Davis</name></author>
    <author><name>Frank Miller</name></author>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
      term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2610.10002v1" rel="alternate" type="text/html"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2610.10003v1</id>
    <updated>2026-10-23T09:00:00Z</updated>
    <published>2026-10-23T09:00:00Z</published>
    <title>Reinforcement Learning for Robotic Grasping with Tactile Feedback</title>
    <summary>We study reinforcement learning policies for robotic grasping
      that exploit tactile feedback under partial observability.</summary>
    <author><name>Grace Kim</name></author>
    <author><name>Henry Park</name></author>
    <author><name>Ivy Choi</name></author>
    <author><name>Jack Sun</name></author>
    <author><name>Kate Liu</name></author>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
      term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.RO" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2610.10003v1" rel="alternate" type="text/html"/>
  </entry>
</feed>
"""

# 与 fixture 配套的关键词（名称, 权重），供打分与渲染测试复用。
# 按此配置，三篇论文的规则分分别为：
#   10001：vision-language (3×3+1×3) + diffusion (3×2+1×2) = 20
#   10002：translation 标题 3×1 + 摘要 1×1 = 4
#   10003：reinforcement 标题 3×1 + 摘要 1×1 = 4
KEYWORDS = [
    ("vision-language", 3.0),
    ("diffusion", 2.0),
    ("translation", 1.0),
    ("reinforcement", 1.0),
]
