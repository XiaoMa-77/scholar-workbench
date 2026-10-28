"""顶刊顶会清单测试：归一化匹配、简写/全称兼容与排除项。"""

from arxiv_digest.venues import is_top_venue, normalize_venue


def test_normalize_venue_strips_punctuation():
    assert normalize_venue("Robotics: Science and Systems XVII") \
        == "robotics science and systems xvii"
    assert normalize_venue("  IEEE  TPAMI ") == "ieee tpami"


def test_top_journals_match():
    for venue in [
        "Nature", "Science", "PNAS", "Nature Machine Intelligence",
        "Nature Robotics", "Science Robotics",
        "IEEE Transactions on Pattern Analysis and Machine Intelligence",
        "International Journal of Computer Vision",
        "Journal of Machine Learning Research",
        "Artificial Intelligence", "IEEE Transactions on Robotics",
        "The International Journal of Robotics Research",
        "IEEE Robotics and Automation Letters",
        "Robotics and Computer-Integrated Manufacturing",
        "Autonomous Robots", "Soft Robotics",
    ]:
        assert is_top_venue(venue), venue


def test_top_conferences_match_abbreviation_and_full_name():
    for venue in [
        "NeurIPS", "ICML", "ICLR", "CVPR", "ECCV", "AAAI", "IJCAI",
        "ICRA", "IROS", "CoRL", "RSS",
        "Advances in Neural Information Processing Systems 36",
        "International Conference on Machine Learning",
        "International Conference on Learning Representations",
        "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "IEEE/RSJ International Conference on Intelligent Robots and Systems",
        "Robotics: Science and Systems",
    ]:
        assert is_top_venue(venue), venue


def test_non_top_venues_rejected():
    for venue in ["", "arXiv", "Unknown Workshop", "Journal of填充 Unknown",
                  "IEEE Access", "Sensors", "Applied Sciences"]:
        assert not is_top_venue(venue), venue
