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

    # 데이터 로드
    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return

    if not data:
        return

    to_archive = []
    to_
