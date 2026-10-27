from src.pipeline.stage7_moments import stream_hashtags
from src.posting import parse_tags, platform_caption


def test_stream_hashtags_order_and_filter():
    tags = stream_hashtags("Kai Cenat", ["#Minecraft", "fyp", "speed run", "kaicenat"], twitch=True)
    assert tags == ["kaicenat", "minecraft", "speedrun", "twitchclips"]
    assert stream_hashtags("", ["viral"]) == []


def test_platform_caption_caps_and_dedupes():
    tags = ["kaicenat", "minecraft", "speedrun", "rage", "fail", "twitchclips"]
    assert platform_caption("He lost it", tags, "youtube") == "He lost it #kaicenat #minecraft #speedrun"
    assert platform_caption("He lost it", tags, "tiktok").count("#") == 5
    # tags already typed in the caption count toward the cap and are not repeated
    assert platform_caption("He lost it #Minecraft", tags, "youtube") == "He lost it #Minecraft #kaicenat #speedrun"
    assert platform_caption("x", [], "instagram", "Music: A by B") == "x\n\nMusic: A by B"


def test_parse_tags_ignores_non_lists():
    assert parse_tags('["#a", "b", ""]') == ["a", "b"]
    assert parse_tags('{"chat": 1}') == [] and parse_tags("not json") == [] and parse_tags(None) == []
