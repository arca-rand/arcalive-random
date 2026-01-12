import json
import sys
import os
import hashlib
import random
import datetime
import subprocess

# 파일 경로 설정
RESULTS_FILE = 'data/results.json'
ARCHIVE_DIR = 'data/archive'

def get_git_revision_hash():
    """현재 커밋 해시를 가져옵니다 (재현성 확보용)"""
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()
    except:
        return "unknown"

def generate_seeds(secret_seed_input):
    """공개 시드(시간)와 비밀 시드를 조합하여 결과 시드를 생성합니다."""
    # 공개 시드: 현재 UTC 시간 (ISO 포맷)
    public_seed = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # PBKDF2 HMAC-SHA256 연산
    dk = hashlib.pbkdf2_hmac(
        'sha256', 
        secret_seed_input.encode('utf-8'), 
        public_seed.encode('utf-8'), 
        100000
    )
    result_seed = dk.hex()
    
    return public_seed, result_seed

def pick_winners(participants, excludes, winner_count, result_seed):
    """결과 시드를 기반으로 당첨자를 선정합니다."""
    # 1. 제외자 필터링 및 정렬 (재현성 위해 정렬 필수)
    valid_pool = sorted(list(set(p for p in participants if p not in excludes)))
    
    # 2. 당첨자 수 결정
    count = min(winner_count, len(valid_pool))
    
    # 3. 시드 설정 (해시값을 정수로 변환)
    seed_int = int(result_seed, 16)
    random.seed(seed_int)
    
    # 4. 추첨
    winners = random.sample(valid_pool, count)
    
    return winners, valid_pool

def manage_archives():
    """
    [분기별 아카이브 로직]
    1, 4, 7, 10월 15일에 실행되어 '직전 분기' 데이터를 아카이브합니다.
    파일명 예시: archive_2025_Q4.json
    """
    if not os.path.exists(RESULTS_FILE):
        return

    # 현재 날짜 확인 (UTC 기준 실행 시간을 고려하여 계산)
    now = datetime.datetime.now(datetime.timezone.utc)
    # 한국 시간(KST)은 UTC+9이므로 보정하여 판단
    kst_now = now + datetime.timedelta(hours=9)
    current_month = kst_now.month
    current_year = kst_now.year

    # 아카이브 대상 분기 결정
    # 1월 실행 -> 작년 Q4 (10~12월)
    # 4월 실행 -> 올해 Q1 (1~3월)
    # 7월 실행 -> 올해 Q2 (4~6월)
    # 10월 실행 -> 올해 Q3 (7~9월)
    
    target_year = current_year
    target_q = 0
    start_month, end_month = 0, 0

    if current_month == 1:
        target_year = current_year - 1
        target_q = 4
        start_month, end_month = 10, 13
    elif current_month == 4:
        target_q = 1
        start_month, end_month = 1, 4
    elif current_month == 7:
        target_q = 2
        start_month, end_month = 4, 7
    elif current_month == 10:
        target_q = 3
        start_month, end_month = 7, 10
    else:
        print(f"정기 관리 월이 아닙니다. (현재 {current_month}월)")
        return

    print(f"아카이브 시작: {target_year}년 Q{target_q} (대상 월: {start_month}~{end_month-1}월)")

    # 오래된 아카이브 삭제 로직 (2년/8분기 전 데이터 삭제)
    # 예: 현재 2026_Q1이면 2024_Q1 이전(미만) 파일 삭제
    if os.path.exists(ARCHIVE_DIR):
        retention_year = target_year - 2
        # 삭제 기준이 될 파일명 생성 (예: archive_2024_Q1.json)
        limit_filename = f"archive_{retention_year}_Q{target_q}.json"
        
        print(f"오래된 데이터 정리 중... (기준: {limit_filename} 미만 삭제)")
        
        for filename in os.listdir(ARCHIVE_DIR):
            if filename.startswith("archive_") and filename.endswith(".json"):
                # 문자열 비교: archive_2023_Q4.json < archive_2024_Q1.json 이므로 삭제됨
                if filename < limit_filename:
                    os.remove(os.path.join(ARCHIVE_DIR, filename))
                    print(f"삭제됨: {filename}")

    # 데이터 로드
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return

    if not data:
        return

    to_archive = []
    to_keep = []

    # 데이터 분류
    for entry in data:
        try:
            entry_time = datetime.datetime.fromisoformat(entry['timestamp'])
            # 해당 분기 데이터인지 확인
            if (entry_time.year == target_year and 
                start_month <= entry_time.month < end_month):
                to_archive.append(entry)
            else:
                to_keep.append(entry)
        except (ValueError, KeyError):
            to_keep.append(entry)

    if not to_archive:
        print("해당 분기에 아카이브할 데이터가 없습니다.")
        return

    # 아카이브 저장
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_filename = f"archive_{target_year}_Q{target_q}.json"
    archive_path = os.path.join(ARCHIVE_DIR, archive_filename)

    # 기존 아카이브 파일이 있으면 합침
    final_archive_data = to_archive
    if os.path.exists(archive_path):
        with open(archive_path, 'r', encoding='utf-8') as f:
            try:
                existing = json.load(f)
                final_archive_data = existing + to_archive
            except:
                pass

    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(final_archive_data, f, indent=2, ensure_ascii=False)
    
    # 메인 파일 업데이트 (남은 데이터 저장)
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(to_keep, f, indent=2, ensure_ascii=False)
    
    print(f"총 {len(to_archive)}개의 항목을 {archive_filename}으로 이동했습니다.")

def main():
    # GitHub Actions에서 보낸 인자(JSON) 읽기
    try:
        input_json_str = sys.argv[1]
        input_data = json.loads(input_json_str)
    except (IndexError, json.JSONDecodeError):
        input_data = {}

    # [유지보수 모드] maintenance 플래그가 true면 관리 로직만 수행 후 종료
    if input_data.get('maintenance') is True:
        print("유지보수 모드로 실행합니다...")
        manage_archives()
        sys.exit(0)

    # [추첨 모드] 데이터 추출
    secret_seed_input = input_data.get('secret_seed', '')
    participants = input_data.get('participants', [])
    excludes = input_data.get('excludes', [])
    winner_count = int(input_data.get('winner_count', 1))
    
    if not participants:
        print("참여자가 없어 추첨을 중단합니다.")
        sys.exit(0)

    # 시드 생성 및 추첨 실행
    public_seed, result_seed = generate_seeds(secret_seed_input)
    winners, final_pool = pick_winners(participants, excludes, winner_count, result_seed)

    # 결과 엔트리 생성 (요청에 따라 requester, participant_count 제거)
    result_entry = {
        "id": f"{int(datetime.datetime.now().timestamp())}", # 고유 식별자
        "git_version": get_git_revision_hash(),             # 코드 버전 기록
        "timestamp": public_seed,                           # 공개 시드 (실행 시간)
        "winners": winners,                                 # 당첨자 목록
        "participants": final_pool,                         # 최종 참여자 명단
        "excludes": excludes,                               # 제외 명단
        "result_seed": result_seed,                         # 검증용 최종 시드
        "link": input_data.get('link')                      # 원문 링크
    }

    # 결과 저장
    if not os.path.exists('data'):
        os.makedirs('data')
        
    current_data = []
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            try:
                current_data = json.load(f)
            except json.JSONDecodeError:
                current_data = []

    current_data.append(result_entry)

    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(current_data, f, indent=2, ensure_ascii=False)
    
    print(f"추첨 완료. 당첨자: {winners}")

if __name__ == "__main__":
    main()
