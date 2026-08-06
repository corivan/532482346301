# -*- coding: utf-8 -*-
"""子实例脚本 - 由父实例生成，请勿手动编辑。"""
import json, os, sys, time, traceback
try:
    import requests
    from func_timeout import func_timeout, FunctionTimedOut
    from random_useragent import UserAgent
except ImportError as e:
    print(f"缺少 {e.name} 库，请先 pip install {e.name}")
    sys.exit(1)
WORK_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work_eyJzdWJOdW0iOiA5_035.json")
DISPATCH_ID = "eyJzdWJOdW0iOiA5MSwgInRpbWUiOiAxNzg2MDEyMjk0fQ=="
SUB_INDEX, SUB_NUM = 35, 91

REQUEST_COUNT = 0

SESSION = requests.Session()
UA = UserAgent()

def _bump_request_count():
    """将本实例自启动以来的网络请求总数 +1。

    仅在内存中累加，落盘由 save_work_json() 在内部统一处理（见 flush_request_count()）。
    """
    global REQUEST_COUNT
    REQUEST_COUNT += 1

def flush_request_count(work):
    """把内存中累计的 REQUEST_COUNT 同步进 work 字典，便于下次落盘。"""
    work["requestCount"] = int(REQUEST_COUNT)

def save_work_json(path, work):
    flush_request_count(work)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(work, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)

def get_instance_info(product_id, auth_code):
    url = f"https://ucapi.bookan.com.cn/uc/getinstanceInfobycode?productId={product_id}&authCode={auth_code}"
    try:
        _bump_request_count()
        resp = func_timeout(5, SESSION.get, args=[url]).json()
        if resp.get("code") != 4000:
            time.sleep(0.75)
            return resp
        else:
            print(f"请求失败，{resp.get('msg')}")
            sys.exit(1)
    except (FunctionTimedOut, OSError) as e:
        print(f"{type(e).__name__}: {e}，暂停60秒后重试")
        time.sleep(60)
        return get_instance_info(product_id, auth_code)

def process_one_auth_code(work, auth_code, expired_list):
    org_data = work["orgData"]
    other = work["otherProductInstance"]
    processed = work.setdefault("processedAuthCodes", [])
    if auth_code in processed:
        return
    done = len(processed) + 1
    total = len(work.get("assignedProductIdsList").keys() or [])
    short = auth_code[:8] + "..." if isinstance(auth_code, str) and len(auth_code) > 8 else str(auth_code)
    prefix = f"[{SUB_INDEX}/{SUB_NUM}] [{done}/{total}] 当前 authCode: {short}"

    assigned_map = work.get("assignedProductIdsList") or {}
    if isinstance(assigned_map, dict):
        todo_pids = list(assigned_map.get(auth_code) or [])
    else:
        todo_pids = []

    # 找到本实例 orgData 中与该 authCode 关联的 org（用于回填 orgName / pageTitle）
    linked_orgs = [info for info in org_data.values() if info.get("organizationAuthCode") == auth_code]

    if linked_orgs:
        # 先用 productId=4 校验授权码
        resp = get_instance_info(4, auth_code)
        if resp.get("code") != 0:
            for org_info in linked_orgs:
                expired_list.append({
                    "orgId": org_info.get("instanceId"),
                    "orgName": org_info.get("orgName"),
                    "organizationAuthCode": auth_code,
                })
            # processed.append(auth_code)
            # work["processedAuthCodes"] = processed
            # save_work_json(WORK_JSON, work)
            # return

        # 用 productId=4 的返回更新关联 org 的 orgName / pageTitle
        for org_info in linked_orgs:
            for item in resp.get("data", []):
                if item.get("instanceId") == org_info.get("instanceId"):
                    org_info["orgName"] = item.get("organizationName") or ""
                    org_info["pageTitle"] = item.get("productTitle") or ""

    for pid in todo_pids:
        resp = get_instance_info(pid, auth_code)
        if resp.get("code") != 0:
            print(f"{prefix} productId: {pid}, 此处没有实例", end="\r", flush=True)
            continue
        for item in resp.get("data", []):
            iid = str(item.get("instanceId"))
            try:
                iid_int = int(iid)
            except (TypeError, ValueError):
                continue
            if iid in org_data.keys() or iid_int in org_data.keys():
                continue
            info = {
                "orgName": item.get("organizationName") or "",
                "productId": pid,
                "organizationAuthCode": item.get("organizationAuthCode"),
                "organizationUserId": item.get("organizationUserId"),
            }
            other[iid] = info
            print(f"{prefix} productId: {pid}, instanceId: {iid}, orgName: {info['orgName']}")

    processed.append(auth_code)
    work["processedAuthCodes"] = processed
    save_work_json(WORK_JSON, work)

def main():
    if not os.path.exists(WORK_JSON):
        print(f"工作副本不存在: {WORK_JSON}\n请先运行父实例的分派任务模式。")
        return
    with open(WORK_JSON, encoding="utf-8") as f:
        work = json.load(f)
    if work.get("dispatchId") != DISPATCH_ID:
        print(f"工作副本的 dispatchId 不一致。\n  本实例: {DISPATCH_ID}\n  文件中: {work.get('dispatchId')}")
        return

    global REQUEST_COUNT
    try:
        REQUEST_COUNT = int(work.get("requestCount", 0))
    except (TypeError, ValueError):
        REQUEST_COUNT = 0

    # 规范化 otherProductInstance
    opi = work.get("otherProductInstance") or {}
    if isinstance(opi, dict):
        norm = {str(k): v for k, v in opi.items()}
        if len(norm) != len(opi):
            print(f"[cleanup] otherProductInstance 去重: {len(opi)} -> {len(norm)}")
        work["otherProductInstance"] = norm
    else:
        work["otherProductInstance"] = {}
    save_work_json(WORK_JSON, work)

    work["orgData"] = {int(k): v for k, v in (work.get("orgData") or {}).items()}

    assigned_auth_codes = list(work.get("assignedProductIdsList").keys() or [])
    processed = []
    seen = set()
    for x in (work.get("processedAuthCodes") or []):
        if x not in seen:
            seen.add(x)
            processed.append(x)
    work["processedAuthCodes"] = processed
    save_work_json(WORK_JSON, work)

    expired_list = []

    try:
        for auth_code in assigned_auth_codes:
            if auth_code in work["processedAuthCodes"]:
                continue
            process_one_auth_code(work, auth_code, expired_list)
    except KeyboardInterrupt:
        print("\n用户中断，已保存当前进度。")
    except Exception:
        traceback.print_exc()
        print("子实例异常退出，已保存当前进度，下次启动可继续。")
    finally:
        save_work_json(WORK_JSON, work)
        print(f"\n子实例 {SUB_INDEX}/{SUB_NUM} 结束，网络请求数: {REQUEST_COUNT}。")
        if expired_list:
            print(f"本次发现 {len(expired_list)} 个失效 authCode:")
            for item in expired_list:
                print(f"  {item.get('orgId')}: {item.get('orgName')}")

if __name__ == "__main__":
    main()
