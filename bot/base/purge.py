import gc
import os
import sys
import time

import bot.base.log as logger

log = logger.get_logger(__name__)
RESTARTING = False


def save_task_data(task):
    try:
        import json
        d = {
            "task_id": getattr(task, "task_id", None),
            "status": getattr(getattr(task, "task_status", None), "name", None),
            "reason": getattr(getattr(task, "end_task_reason", None), "value", None),
            "start": getattr(task, "task_start_time", None),
            "end": getattr(task, "end_task_time", None),
            "app": getattr(task, "app_name", None),
            "type": getattr(getattr(task, "task_type", None), "name", None),
        }
        with open("userdata/last_task.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def soft_process_restart():
    try:
        global RESTARTING
        if RESTARTING:
            return
        RESTARTING = True
        os.makedirs('userdata', exist_ok=True)
        try:
            with open('userdata/restart.lock', 'w') as f:
                f.write(str(os.getpid()))
        except Exception:
            pass
        import subprocess, sys as _sys
        env = os.environ.copy()
        env['UAT_AUTORESTART'] = '1'
        subprocess.Popen([_sys.executable, "main.py"], env=env)
        os._exit(0)
    except Exception:
        try:
            os._exit(0)
        except Exception:
            pass


def acquire_instance_lock():
    try:
        os.makedirs('userdata', exist_ok=True)
        try:
            os.remove('userdata/restart.lock')
        except Exception:
            pass
        p = 'userdata/instance.lock'
        old = None
        if os.path.exists(p):
            try:
                with open(p, 'r') as f:
                    old = int((f.read() or '0').strip() or '0')
            except Exception:
                old = None
        if old:
            try:
                import psutil
                if psutil.pid_exists(old):
                    if os.environ.get('UAT_AUTORESTART','0') == '1':
                        limit = time.time() + 20
                        while time.time() < limit and psutil.pid_exists(old):
                            time.sleep(0.5)
            except Exception:
                pass
        if os.path.exists(p):
            try:
                cur = None
                with open(p, 'r') as f:
                    cur = int((f.read() or '0').strip() or '0')
            except Exception:
                cur = None
            try:
                import psutil
                if not cur or not psutil.pid_exists(cur):
                    os.remove(p)
            except Exception:
                try:
                    os.remove(p)
                except Exception:
                    pass
        with open(p, 'x') as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        return True
    except Exception:
        return True


def serialize_umamusume_task(t):
    try:
        d = t.detail
        sc = getattr(d, 'scenario_config', None)
        ura = getattr(sc, 'ura_config', None) if sc else None
        aoharu = getattr(sc, 'aoharu_config', None) if sc else None
        attachment = {
            'scenario': int(getattr(d, 'scenario', 0).value) if hasattr(getattr(d, 'scenario', 0), 'value') else int(getattr(d, 'scenario', 0)),
            'expect_attribute': getattr(d, 'expect_attribute', None),
            'follow_support_card_level': int(getattr(d, 'follow_support_card_level', 0)),
            'follow_support_card_name': getattr(d, 'follow_support_card_name', ''),
            'extra_race_list': getattr(d, 'extra_race_list', []) or [],
            'learn_skill_list': getattr(d, 'learn_skill_list', []) or [],
            'learn_skill_blacklist': getattr(d, 'learn_skill_blacklist', []) or [],
            'tactic_list': getattr(d, 'tactic_list', []) or [],
            'clock_use_limit': int(getattr(d, 'clock_use_limit', 0)),
            'learn_skill_threshold': int(getattr(d, 'learn_skill_threshold', 0)),
            'learn_skill_only_user_provided': bool(getattr(d, 'learn_skill_only_user_provided', False)),
            'allow_recover_tp': bool(getattr(d, 'allow_recover_tp', False)),
            'extra_weight': getattr(d, 'extra_weight', []) or [],
            'manual_purchase_at_end': bool(getattr(d, 'manual_purchase_at_end', False)),
            'cure_asap_conditions': getattr(d, 'cure_asap_conditions', ''),
            'motivation_threshold_year1': int(getattr(d, 'motivation_threshold_year1', 3)),
            'motivation_threshold_year2': int(getattr(d, 'motivation_threshold_year2', 4)),
            'motivation_threshold_year3': int(getattr(d, 'motivation_threshold_year3', 4)),
            'prioritize_recreation': bool(getattr(d, 'prioritize_recreation', False)),
            'score_value': getattr(d, 'score_value', None),
            'ura_config': None,
            'aoharu_config': None,
            'fujikiseki_show_mode': bool(getattr(d, 'fujikiseki_show_mode', False)),
            'fujikiseki_show_difficulty': int(getattr(d, 'fujikiseki_show_difficulty', 1)),
        }
        if ura is not None:
            attachment['ura_config'] = {
                'skillEventWeight': getattr(ura, 'skill_event_weight', [0, 0, 0]),
                'resetSkillEventWeightList': getattr(ura, 'reset_skill_event_weight_list', []) or []
            }
        if aoharu is not None:
            attachment['aoharu_config'] = {
                'preliminaryRoundSelections': getattr(aoharu, 'preliminary_round_selections', []) or [],
                'aoharuTeamNameSelection': int(getattr(aoharu, 'aoharu_team_name_selection', 0))
            }
        return attachment
    except Exception:
        return None


def save_scheduler_state():
    try:
        from bot.engine.scheduler import scheduler
        import json
        os.makedirs('userdata', exist_ok=True)
        with open('userdata/scheduler_state.json', 'w', encoding='utf-8') as f:
            json.dump({'active': bool(getattr(scheduler, 'active', False))}, f)
        return True
    except Exception:
        return False


def load_scheduler_state():
    try:
        import json
        path = 'userdata/scheduler_state.json'
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        try:
            os.remove(path)
        except Exception:
            pass
        return bool(d.get('active'))
    except Exception:
        return None


def save_scheduler_tasks():
    try:
        from bot.engine.scheduler import scheduler
        import json
        tasks = []
        for t in scheduler.get_task_list() or []:
            try:
                app = getattr(t, 'app_name', None)
                mode = getattr(getattr(t, 'task_execute_mode', None), 'value', None)
                ttype = getattr(getattr(t, 'task_type', None), 'value', None)
                desc = getattr(t, 'task_desc', '')
                cron = getattr(t, 'cron_job_config', None)
                cron_dump = None
                if cron is not None:
                    cron_dump = getattr(cron, 'cron', None)
                attachment = None
                if app == 'umamusume':
                    attachment = serialize_umamusume_task(t)
                entry = {
                    'task_id': getattr(t, 'task_id', None),
                    'app_name': app,
                    'task_execute_mode': mode,
                    'task_type': ttype,
                    'task_desc': desc,
                    'attachment_data': attachment,
                    'cron_job_config': {'cron': cron_dump} if cron_dump else None
                }
                tasks.append(entry)
            except Exception:
                continue
        os.makedirs('userdata', exist_ok=True)
        with open('userdata/saved_tasks.json', 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_saved_tasks():
    try:
        import json
        import bot.engine.ctrl as ctrl
        from bot.base.task import TaskExecuteMode as TEM
        from bot.base.common import CronJobConfig
        path = 'userdata/saved_tasks.json'
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for it in data or []:
            try:
                mode_raw = it.get('task_execute_mode')
                try:
                    if isinstance(mode_raw, int):
                        mode = TEM(mode_raw)
                    elif isinstance(mode_raw, str):
                        mode = TEM[mode_raw]
                    else:
                        mode = TEM.TASK_EXECUTE_MODE_ONE_TIME
                except Exception:
                    mode = TEM.TASK_EXECUTE_MODE_ONE_TIME
                cron_src = it.get('cron_job_config')
                cron_obj = None
                if cron_src and isinstance(cron_src, dict) and cron_src.get('cron'):
                    cron_obj = CronJobConfig()
                    cron_obj.cron = cron_src.get('cron')
                    cron_obj.next_time = None
                    cron_obj.last_time = None
                ctrl.add_task(
                    it.get('app_name'),
                    mode,
                    it.get('task_type'),
                    it.get('task_desc'),
                    cron_obj,
                    it.get('attachment_data')
                )
                try:
                    from bot.engine.scheduler import scheduler
                    t = scheduler.get_task_list()[-1]
                    tid = it.get('task_id')
                    if tid:
                        t.task_id = tid
                    if mode in (TEM.TASK_EXECUTE_MODE_ONE_TIME, TEM.TASK_EXECUTE_MODE_LOOP, TEM.TASK_EXECUTE_MODE_TEAM_TRIALS):
                        from bot.base.task import TaskStatus as TS
                        t.task_status = TS.TASK_STATUS_PENDING
                except Exception:
                    pass
            except Exception:
                continue
        try:
            os.remove(path)
        except Exception:
            pass
        return True
    except Exception:
        return False


def purge_all(reason: str = ""):
    try:
        if os.environ.get('UAT_DISABLE_MKLDNN', None) is None:
            os.environ['UAT_DISABLE_MKLDNN'] = '1'
            log.info("purge: set UAT_DISABLE_MKLDNN=1 for next OCR init")
    except Exception:
        pass

    try:
        from bot.recog.ocr import reset_ocr
        reset_ocr()
        log.info("purge: OCR reset")
    except Exception:
        pass

    try:
        pass
    except Exception:
        pass

    try:
        import bot.conn.fetch as fetch
        sc = getattr(fetch, 'shared_controller', None)
        if sc is not None:
            try:
                sc.destroy()
            except Exception:
                pass
            try:
                fetch.shared_controller = None
            except Exception:
                pass
            log.info("purge: shared controller released")
    except Exception:
        pass

    try:
        pass
    except Exception:
        pass

    try:
        pass
    except Exception:
        pass

    try:
        import cv2
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
    except Exception:
        pass

    try:
        gc.collect()
        gc.collect()
    except Exception:
        pass

    try:
        if os.name == 'nt':
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentProcess()
            try:
                ctypes.windll.kernel32.SetProcessWorkingSetSize(h, -1, -1)
            except Exception:
                pass
            try:
                ctypes.windll.psapi.EmptyWorkingSet(h)
            except Exception:
                pass
    except Exception:
        pass

    try:
        import importlib
        importlib.invalidate_caches()
    except Exception:
        pass

    try:
        import time
        time.sleep(float(os.getenv("UAT_PURGE_PAUSE_SEC", "0.15")))
    except Exception:
        pass
