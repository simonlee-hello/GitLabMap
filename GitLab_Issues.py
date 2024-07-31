import argparse
import requests
import json
import csv
import time
import os
import re
from colorama import init, Fore, Style

def log_info(message):
    print(f"{Fore.GREEN}[INFO] {message}")

def log_warning(message):
    print(f"{Fore.YELLOW}[WARNING] {message}")

def log_error(message):
    print(f"{Fore.RED}[ERROR] {message}")

def make_directory(path):
    os.makedirs(path, exist_ok=True)


# 定义一个函数，用于在字符串中匹配图片 URL
def find_image_urls(text):
    return re.findall(r'\[.*?\]\((/uploads/.*?)\)', text)


def fetch_project_data(base_url, project_id, headers):
    project_url = f'{base_url}/api/v4/projects/{project_id}'
    response = requests.get(project_url, headers=headers, params={'page': 1, 'per_page': 1})
    project_data = response.json()
    if not project_data or "message" in project_data and project_data["message"] == "404 Project Not Found":
        log_warning(f"项目 {project_id} : 404 Not Found")
        return None
    return project_data


def fetch_issues(issues_url, headers):
    issues = []
    page = 1
    while True:
        response = requests.get(issues_url, headers=headers, params={'page': page, 'per_page': 100})
        data = response.json()
        if not data:
            break
        issues.extend(data)
        page += 1
        time.sleep(0.3)
    return issues


def fetch_issue_notes(issues, issues_url, headers):
    for issue in issues:
        notes = []
        issue_id = issue['iid']
        notes_url = f'{issues_url}/{issue_id}/notes'
        notes_page = 1
        while True:
            notes_response = requests.get(notes_url, headers=headers, params={'page': notes_page, 'per_page': 100})
            notes_data = notes_response.json()
            if "message" in notes_data and notes_data["message"] == "404 Not found":
                log_warning(f"Issue {issue_id} - Page {notes_page}: 404 Not Found")
                break
            if not notes_data:
                break
            notes.extend(notes_data)
            notes_page += 1
            time.sleep(0.3)
        issue['notes'] = notes


def save_json(data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def load_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def write_to_csv(issues, csv_path):
    with open(csv_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([
            'Issue ID', 'Title', 'Description', 'State', 'Created At', 'Updated At', 'Closed At',
            'Author', 'Assignee', 'Labels', 'Milestone', 'Due Date', 'Web URL', 'Note ID', 'Note Body', 'Note Author',
            'Note Created At'
        ])
        all_image_urls = []
        for issue in issues:
            milestone_title = issue['milestone']['title'] if issue.get('milestone') else ''
            issue_base_data = [
                issue['id'],
                issue['title'],
                issue.get('description', ''),
                issue['state'],
                issue['created_at'],
                issue['updated_at'],
                issue.get('closed_at', ''),
                issue['author']['username'],
                ', '.join([assignee['username'] for assignee in issue.get('assignees', [])]),
                ', '.join(issue.get('labels', [])),
                milestone_title,
                issue.get('due_date', ''),
                issue['web_url']
            ]
            if 'description' in issue:
                all_image_urls.extend(find_image_urls(issue['description']))
            if issue['notes']:
                for note in issue['notes']:
                    writer.writerow(
                        issue_base_data + [note['id'], note['body'], note['author']['username'], note['created_at']])
                    all_image_urls.extend(find_image_urls(note['body']))
            else:
                writer.writerow(issue_base_data + ['', '', '', ''])
    return all_image_urls


def download_images(image_urls, project_web_url, headers, output_dir):
    make_directory(output_dir)
    for image_url in image_urls:
        full_image_url = f'{project_web_url}{image_url}'
        image_response = requests.get(full_image_url, headers=headers)
        if image_response.status_code == 200:
            image_path = os.path.join(output_dir, *image_url.split('/'))
            make_directory(os.path.dirname(image_path))
            with open(image_path, 'wb') as image_file:
                image_file.write(image_response.content)
                log_info(f"成功保存 {image_path}")
        else:
            log_error(f"获取图片失败: {full_image_url}, 状态码: {image_response.status_code}")
        time.sleep(0.2)


def download_issues_and_notes(base_url, cookie, project_id, output_dir):
    headers = {
        'Cookie': f'_gitlab_session={cookie}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/115.0.0.0 Safari/537.36'
    }

    # 获取项目信息
    project_data = fetch_project_data(base_url, project_id, headers)
    if not project_data:
        return
    project_web_url = project_data['web_url']

    issues_url = f'{base_url}/api/v4/projects/{project_id}/issues'

    # 下载并保存 Issues 和 Notes
    issues = fetch_issues(issues_url, headers)
    save_json(issues, os.path.join(output_dir, f'issues_{project_id}.json'))

    fetch_issue_notes(issues, issues_url, headers)
    save_json(issues, os.path.join(output_dir, f'issues_with_notes_{project_id}.json'))

    # 写入 CSV 并下载图片
    all_image_urls = write_to_csv(issues, os.path.join(output_dir, f'issues_with_notes_and_images_{project_id}.csv'))
    download_images(all_image_urls, project_web_url, headers, os.path.join(output_dir, 'issue_images'))

    log_info(f"项目 {project_id} 的所有数据已处理完毕并保存到 {output_dir}")


def main():
    parser = argparse.ArgumentParser(description='Download GitLab issues and notes for specified projects.')
    parser.add_argument('--url', required=True, help='GitLab base URL')
    parser.add_argument('--session', required=True, help='GitLab session cookie')
    parser.add_argument('--ids', required=True, help='Comma-separated list of project IDs')
    parser.add_argument('-o', '--output', default='output', help='Output directory')

    args = parser.parse_args()

    project_ids = args.ids.split(',')
    output_dir = args.output

    make_directory(output_dir)

    for project_id in project_ids:
        log_info(f'正在处理项目 {project_id}')
        download_issues_and_notes(args.url, args.session, project_id, output_dir)


if __name__ == '__main__':
    main()
