"""
选题刷新相关 Action
"""

class RefreshTopicsAction:
    """换一批选题"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        open_id = getattr(session, "open_id", "")
        # 在独立线程中生成选题
        import threading as _th
        import ideator as _ideator
        _th.Thread(target=_ideator.send_morning_topics, args=(open_id,)).start()
        return {"toast": {"type": "success", "content": "为您搜罗一批新点子中..."}}


class RequestIdeasAction:
    """主动获取选题（等效于换一批）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        return RefreshTopicsAction().execute(session, data, mgr, **context)


class OpenTopicBlindBoxAction:
    """总入口「主题」→ 打开 10 条盲盒选题（第二步）"""

    def execute(self, session, data: dict, mgr, **context) -> dict:
        return RefreshTopicsAction().execute(session, data, mgr, **context)
