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
    """
    공개 시드(시간)와 비밀 시드를 조합하여 결과 시드를 생성합니다.
    PBKDF2를 사용하여 무차별 대입 공격을 방지합니다.
    """
    # 공개 시드: 현재 UTC 시간 (ISO 포맷)
    public_seed = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 비밀 시드 + 공개 시드 조합 (PBKDF2 HMAC-SHA256)
    # salt로 공개 시드를 사용, 반복 횟수 100,000회
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
    
    # 1. 제외자 필터링 및 중복 제거 (닉네임 기준)
    valid_pool = sorted(list(set(p for p in participants if p not in excludes)))
    
    # 2. 참여자가 당첨자 수보다 적을 경우 예외 처리
    count = min(winner_count, len(valid_pool))
    
    # 3. 시드 설정 (결과 시드의 해시값을 정수로 변환하여 시드로 사용)
    # 파이썬의 random은 Mersenne Twister 알고리즘을 사용하며, 시드가 같으면 결과가 동일함
    seed_int = int(result_seed, 16)
    random.seed(seed_int)
    
    # 4. 추첨
    winners = random.sample(valid_pool, count)
    
    return winners, valid_pool

def manage_archives():
    """
    결과 파일 관리를 수행합니다.
    (3개월 분량이 넘어가면 아카이브로 이동, 오래된 아카이브 삭제)
    """
    if not os.path.exists(RESULTS_FILE):
        return

    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return # 파일이 깨져있으면 무시

    if not data:
        return

    # 첫 데이터의 날짜 확인
    first_entry_time = datetime.datetime.fromisoformat(data[0]['timestamp'])
    current_time = datetime.datetime.now(datetime.timezone.utc)
    
    # 3개월(대략 90일) 지났는지 확인
    if (current_time - first_entry_time).days > 90:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        
        # 아카이브 파일명 생성 (예: archive_20251001_20260101.json)
        last_entry_time = datetime.datetime.fromisoformat(data[-1]['timestamp'])
        archive_name = f"archive_{first_entry_time.strftime('%Y%m%d')}_{last_entry_time.strftime('%Y%m%d')}.json"
        archive_path = os.path.join(ARCHIVE_DIR, archive_name)
        
        # 파일 이동 (내용 쓰기)
        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        # 메인 파일 초기화 (빈 리스트로 생성할지는 선택, 여기선 리셋)
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2, ensure_ascii=False)

        # 오래된 아카이브 삭제 (최신 9개 유지)
        archives = sorted([os.path.join(ARCHIVE_DIR, f) for f in os.listdir(ARCHIVE_DIR) if f.endswith('.json')])
        if len(archives) > 9:
            for old_file in archives[:-9]:
                os.remove(old_file)
                print(f"Deleted old archive: {old_file}")

def main():
    # GitHub Actions의 input은 환경 변수나 인자로 받음 (여기선 인자로 가정)
    try:
        input_json_str = sys.argv[1]
        input_data = json.loads(input_json_str)
    except (IndexError, json.JSONDecodeError) as e:
        print(f"Error reading input: {e}")
        sys.exit(1)

    # 1. 아카이브 관리 (저장 전 수행)
    manage_archives()

    # 2. 데이터 추출 및 검증
    secret_seed_input = input_data.get('secret_seed', '')
    participants = input_data.get('participants', [])
    excludes = input_data.get('excludes', [])
    winner_count = int(input_data.get('winner_count', 1))
    
    # 3. 시드 생성 및 추첨
    public_seed, result_seed = generate_seeds(secret_seed_input)
    winners, final_pool = pick_winners(participants, excludes, winner_count, result_seed)

    # 4. 저장할 결과 JSON 생성
    result_entry = {
        "id": f"{int(datetime.datetime.now().timestamp())}", # 시간 기반 ID
        "git_version": get_git_revision_hash(),
        "timestamp": public_seed, # 공개 시드 역할
        "winners": winners,
        "requester": input_data.get('requester'),
        "participant_count": len(final_pool),
        "participants": final_pool, # 실제 추첨 대상이 된 목록
        "excludes": excludes,
        "result_seed": result_seed, # 결과 검증용 핵심 키
        "link": input_data.get('link')
    }

    # 5. 파일 저장 (Append)
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
    
    print(f"Successfully processed raffle. Winners: {winners}")

if __name__ == "__main__":
    main()
