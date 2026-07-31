def parse_duration(value):
    value = str(value).strip()
    if not value:
        return 0
    if ":" in value:
        parts = [int(part) for part in value.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return int(float(value))


def format_duration(seconds):
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    return f"{minutes:02d}:{sec:02d}"


def render_template(text, song):
    if song is None:
        return str(text)
    return str(text).format(
        title=song.title,
        keyword=song.keyword,
        duration=song.duration_seconds,
        buffer=song.buffer_seconds,
        total=song.duration_seconds + song.buffer_seconds,
    )
