# app/main.py
from fastapi import FastAPI
from datetime import date as date_dt
import threading, time, schedule, datetime, logging, os, json, requests

from daily_summary import generate_daily_message
from news_crawler import crawl_news, save_to_json
from news_daily_highlight_v2 import generate_daily_summary_json, makedirs
from news_daily_summarization import add_summaries_in_place
from news_weekly_highlight import generate_weekly_summary_json
from remittance_message import merge_news_highlights, generate_remittance_message
from weekly_summary import generate_weekly_message

app = FastAPI()
API_ENDPOINT = "http://3.38.183.156:8000/"

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

########################################################################################
def scheduled_crawling(date):
    """스케줄링된 뉴스 크롤링 작업"""
    logger.info("뉴스 크롤링 작업을 시작합니다.")

    # 어제 날짜(YYYYMMDD)로 설정
    # date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    # KIA 타이거즈: HT, 삼성 라이온즈: SS, 두산 베어스: OB, 롯데 자이언츠: LT, KT 위즈: KT, SSG 랜더스: SK, 한화 이글스: HH, NC 다이노스: NC, 키움 히어로즈: WO, LG 트윈스: LG
    for team in ["HT", "SS", "OB", "LT", "KT", "SK", "HH", "NC", "WO", "LG"]:
        try:
            results = crawl_news(date, team)
            save_to_json(date, team, results)
            logger.info(f"{date} {team} 크롤링 완료. 총 {len(results)}개의 기사를 저장했습니다.")
        except Exception as e:
            logger.error(f"{team} 크롤링 실패: {e}")
    logger.info("뉴스 크롤링 작업이 완료되었습니다.")

########################################################################################
def scheduled_summarization(date):
    """스케줄링된 일일 뉴스 본문 요약 작업"""
    logger.info("일일 뉴스 본문 요약 작업을 시작합니다.")

    # 어제 날짜(YYYYMMDD)로 설정
    # date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    # 일일 뉴스 요약(news_summary 필드 추가)
    add_summaries_in_place(date)

    logger.info(f"일일 뉴스 본문 요약 작업이 완료되었습니다.")

########################################################################################
def scheduled_daily_highlight(date):
    """스케줄링된 팀별 일일 뉴스 하이라이트 작업"""
    logger.info("팀별 일일 뉴스 하이라이트 작업을 시작합니다.")

    # 어제 날짜(YYYYMMDD)로 설정
    # date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    # 모든 팀의 뉴스 요약 결과를 JSON 구조로 생성
    final_json = generate_daily_summary_json(date)
    json_path = "news_daily_highlight"
    file_path = os.path.join("news_daily_highlight", f"news_daily_highlight_{date}.json")
    makedirs("news_daily_highlight")
    
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump(final_json, json_file, ensure_ascii=False, indent=2)

    logger.info(f"팀별 일일 뉴스 하이라이트 작업이 완료되었습니다.")

########################################################################################
def scheduled_remittance_message(date):
    """스케줄링된 송금 메시지 생성 작업"""
    logger.info("송금 메시지 생성 작업을 시작합니다.")

    # 어제 날짜(YYYYMMDD)로 설정
    # date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    # 필요한 계좌 정보 요청 (GET 요청)
    try:
        date_obj = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        info_response = requests.get(f"{API_ENDPOINT}api/report/all-accounts-summary?game_date={date_obj}",
        headers={'Content-Type': 'application/json'})
        info_response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        account_data = info_response.json()
        logger.info(f"필요한 계좌 정보 요청 성공: {account_data}")
    except requests.exceptions.RequestException as e:
        logger.error(f"계좌 정보 요청 중 오류 발생: {e}")
        return

    # 뉴스 데이터 불러오기
    news_path = f"news_daily_highlight/news_daily_highlight_{date}.json"
    news_data = json.load(open(news_path, encoding="utf-8"))

    # 계좌 정보와 뉴스 하이라이트 병합
    input_data = merge_news_highlights(account_data, news_data)
    report_date = input_data['date']

    # 결과 생성
    remittance_message = []
    for account_id, account in input_data['accounts'].items():
        remittance_message_message_output = generate_remittance_message(account_id, account, report_date)
        remittance_message.append(remittance_message_message_output)

    # output_json = {"remittance_message": remittance_message}
    
    # 생성된 송금 메시지 전송 (POST 요청)
    try:
        post_response = requests.post(f"{API_ENDPOINT}api/account/transactions",
        headers={'Content-Type': 'application/json'},
        json=remittance_message  # json 매개변수를 사용하면, 내부적으로 json.dumps() 처리가 됩니다.
        )
        post_response.raise_for_status()  # HTTP 오류가 있을 경우 예외 발생
        logger.info(f"송금 메시지 전송 성공: {post_response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"송금 메시지 전송 중 오류 발생: {e}")

    logger.info(f"송금 메시지 생성 작업이 완료되었습니다.")

########################################################################################
def scheduled_daily_summary(date):
    """스케줄링된 일일 요약 메시지 생성 작업"""
    logger.info("일일 요약 메시지 생성 작업을 시작합니다.")

    # 필요한 팀 정보 요청 (GET 요청)
    try:
        date_obj = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        info_response = requests.get(API_ENDPOINT + "api/report/team-daily-savings" + f"?date={date_obj}",
        headers={'Content-Type': 'application/json'})
        info_response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        input_data = info_response.json()
        logger.info(f"필요한 계좌 정보 요청 성공: {input_data}")
    except requests.exceptions.RequestException as e:
        logger.error(f"계좌 정보 요청 중 오류 발생: {e}")
        return

    if input_data["teams_data"]:
        data_list = input_data["teams_data"]
        report_date = input_data["date"]   

        reports = []
        for account in data_list:
            # 각 팀의 정보를 기반으로 데일리 메시지 생성
            daily_message_output = generate_daily_message(account, report_date)
            reports.append(daily_message_output)

        output_json = {"reports": reports}
    else:
        # 데이터가 없는 월요일 데이터를 입력받았을 경우
        report_date = input_data["date"]

        reports = []
        for i in range(1, 11):
            team_id = i
            date = report_date
            daily_text = "경기가 없는 하루였지만, 팬 여러분 덕분에 우리 팀은 또 다른 승리를 준비하고 있습니다. 계속 함께 달려볼까요?"
            daily_message_output = {
                "team_id": team_id,
                "date": date,
                "llm_context": daily_text
            }
            reports.append(daily_message_output)
        
        output_json = {"reports": reports}

    # 생성된 일일 요약 메시지 전송 (POST 요청)
    try:
        post_response = requests.post(API_ENDPOINT + "api/report/team/daily",
        headers={'Content-Type': 'application/json'},
        json=output_json  # json 매개변수를 사용하면, 내부적으로 json.dumps() 처리가 됩니다.
        )
        post_response.raise_for_status()  # HTTP 오류가 있을 경우 예외 발생
        logger.info(f"일일 요약 메시지 전송 성공: {post_response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"일일 요약 메시지 전송 중 오류 발생: {e}")

    logger.info(f"일일 요약 메시지 생성 작업이 완료되었습니다.")

########################################################################################
def scheduled_weekly_highlight(date):
    """스케줄링된 팀별 주간 뉴스 하이라이트 작업"""
    logger.info("팀별 주간 뉴스 하이라이트 작업을 시작합니다.")

    # 어제 날짜(YYYYMMDD)로 설정
    # date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    # 모든 팀의 주간 뉴스 하이라이트를 JSON 구조로 생성
    result_json = generate_weekly_summary_json(date)

    date_obj = datetime.datetime.strptime(date, "%Y%m%d")
    week_number = date_obj.isocalendar()[1] - 12

    # 디렉토리 생성 및 JSON 파일 저장
    output_folder = "news_weekly_highlight"
    os.makedirs(output_folder, exist_ok=True)
    file_name = os.path.join(output_folder, f"news_weekly_highlight_{week_number}주차.json")

    with open(file_name, "w", encoding="utf-8") as json_file:
        json.dump(result_json, json_file, ensure_ascii=False, indent=4)
        
    logger.info(f"{file_name} 파일이 생성되었습니다.")

    # 생성된 일일 요약 메시지 전송 (POST 요청)
    try:
        post_response = requests.post(API_ENDPOINT + "api/report/news-summary",
        headers={'Content-Type': 'application/json'},
        json=result_json  # json 매개변수를 사용하면, 내부적으로 json.dumps() 처리가 됩니다.
        )
        post_response.raise_for_status()  # HTTP 오류가 있을 경우 예외 발생
        logger.info(f"팀별 주간 뉴스 하이라이트 전송 성공: {post_response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"팀별 주간 뉴스 하이라이트 전송 중 오류 발생: {e}")


    logger.info(f"팀별 주간 뉴스 하이라이트 작업이 완료되었습니다.")

########################################################################################
def scheduled_weekly_summary(date):
    """스케줄링된 주간 요약 메시지 생성 작업"""
    logger.info("주간 요약 메시지 생성 작업을 시작합니다.")

    date_obj = date[:4] + "-" + date[4:6] + "-" + date[6:]

    # 필요한 팀 정보 요청 (GET 요청)
    try:
        info_response = requests.get(API_ENDPOINT + "api/report/weekly-report-data" + f"?report_date={date_obj}",
        headers={'Content-Type': 'application/json'})
        info_response.raise_for_status()  # HTTP 오류 발생 시 예외 발생
        input_data = info_response.json()
        logger.info(f"필요한 계좌 정보 요청 성공: {input_data}")
    except requests.exceptions.RequestException as e:
        logger.error(f"계좌 정보 요청 중 오류 발생: {e}")
        return

    # 데이터 추출
    data_list = input_data['accounts_data']
    report_date = input_data['report_date']

    # 현재 적금 주차 계산
    _, week_number, _ = date_dt.today().isocalendar()
    current_week = week_number - 12

    # 결과 생성
    reports = []
    for account in data_list:
        weekly_message_output = generate_weekly_message(account, report_date, current_week)
        reports.append(weekly_message_output)
        print(weekly_message_output)

    output_json = {"reports": reports}

    # 생성된 주간 요약 메시지 전송 (POST 요청)
    try:
        post_response = requests.post(API_ENDPOINT + "api/report/personal/weekly",
        headers={'Content-Type': 'application/json'},
        json=output_json  # json 매개변수를 사용하면, 내부적으로 json.dumps() 처리가 됩니다.
        )
        post_response.raise_for_status()  # HTTP 오류가 있을 경우 예외 발생
        logger.info(f"주간 요약 메시지 전송 성공: {post_response.json()}")
    except requests.exceptions.RequestException as e:
        logger.error(f"주간 요약 메시지 전송 중 오류 발생: {e}")

    logger.info(f"주간 요약 메시지 생성 작업이 완료되었습니다.")

########################################################################################
def run_daily_data_tasks():
    """매일 실행할 뉴스 크롤링 및 요약 작업들을 순차적으로 실행하는 함수"""
    logger.info("=== Daily data tasks started ===")
    date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    scheduled_crawling(date)              # 뉴스 크롤링
    scheduled_summarization(date)         # 일일 뉴스 본문 요약
    scheduled_daily_highlight(date)       # 팀별 일일 뉴스 하이라이트

    logger.info("=== Daily data tasks completed ===")

def run_daily_message_tasks():
    """매일 실행할 메시지 생성 작업들을 순차적으로 실행하는 함수"""
    logger.info("=== Daily message tasks started ===")
    date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d") 
    date_obj = datetime.datetime.strptime(date, "%Y%m%d")

    # 월요일 여부 판별(0: 월요일, 1: 화요일, ..., 6: 일요일)
    if date_obj.weekday() == 0:
        scheduled_daily_summary(date)           # 일일 요약 메시지 생성
        scheduled_weekly_highlight(date)        # 팀별 주간 뉴스 하이라이트
        scheduled_weekly_summary(date)          # 주간 요약 메시지 생성
    else:
        scheduled_remittance_message(date)      # 송금 메시지 생성
        scheduled_daily_summary(date)           # 일일 요약 메시지 생성

    logger.info("=== Daily message tasks completed ===")

def run_scheduler():
    """전체 스케줄러 실행 함수"""
    logger.info("스케줄링된 작업이 시작되었습니다.")

    # 매일 실행할 뉴스 크롤링 및 요약 작업을 원하는 시간에 호출하도록 예약
    schedule.every().day.at("01:00").do(run_daily_data_tasks)   
    
    # 매일 실행할 메시지 생성 작업을 원하는 시간에 호출하도록 예약
    schedule.every().day.at("03:00").do(run_daily_message_tasks)

    while True:
        schedule.run_pending()
        time.sleep(60)

    logger.info("스케줄링된 작업이 완료되었습니다.")

@app.on_event("startup")
def startup_event():
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("백그라운드 스케줄러가 시작되었습니다.")

if __name__ == "__main__":
    run_scheduler()
