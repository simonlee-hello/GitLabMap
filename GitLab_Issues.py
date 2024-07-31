import argparse
import requests
import json
import csv
import time
import os
import re


def find_image_urls(text):
    return re.findall(r'\[.*?\]\((/uploads/.*?)\)', text)


def download_issues_and_notes(base_url, cookie, project_id, output_dir):
    headers = {
        'Cookie': f'_gitlab_session={cookie}'
    }

    # 获取项目的基础信息
    project_url = f'{base_url}/api/v4/projects/{project_id}'
    response = requests.get(project_url, headers=headers)
    project_data = response.json()
    if not project_data:
        print(f"项目 {project_id} 获取信息失败")
        return
    elif "message" in project_data and project_data["message"] == "404 Project Not Found":
        print(f"项目 {project_id} : 404 Not Found")
        return
    else:
        project_web_url = project_data['web_url']

    issues_url = f'{project_url}/issues'

    # 创建保存数据的目录
    os.makedirs(output_dir, exist_ok=True)
    json_dir = os.path.join(output_dir, 'json_data')
    image_dir = os.path.join(output_dir, 'issue_images')
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(image_dir, exist_ok=True)

    # 获取项目的所有issues
    issues = []
    page = 1

    while True:
        response = requests.get(issues_url, headers=headers, params={'page': page, 'per_page': 100})
        data = response.json()
        if not data:
            break
        issues.extend(data)
        page += 1
        time.sleep(0.3)  # 避免触发API速率限制

    # 保存issues到本地文件
    issues_json_path = os.path.join(json_dir, f'issues_{project_id}.json')
    with open(issues_json_path, 'w', encoding='utf-8') as file:
        json.dump(issues, file, ensure_ascii=False, indent=4)

    # 获取每个issue的评论（notes）并保存到本地文件
    for issue in issues:
        issue_id = issue['iid']
        notes_url = f'{issues_url}/{issue_id}/notes'

        notes = []
        notes_page = 1
        while True:
            notes_response = requests.get(notes_url, headers=headers, params={'page': notes_page, 'per_page': 100})
            notes_data = notes_response.json()
            if "message" in notes_data and notes_data["message"] == "404 Not found":
                print(f"Issue {issue_id} - Page {notes_page}: 404 Not Found")
                break

            if not notes_data:
                break
            notes.extend(notes_data)
            print(f'Issue {issue_id} - 已处理第 {notes_page} 页的评论，共 {len(notes_data)} 条评论')  # 打印处理进度
            notes_page += 1
            time.sleep(0.3)  # 避免触发API速率限制

        issue['notes'] = notes
    print(f'所有 Issue 已处理完 - 项目 {project_id}')  # 打印处理进度

    # 保存issues和notes的组合数据到本地文件
    issues_with_notes_json_path = os.path.join(json_dir, f'issues_with_notes_{project_id}.json')
    with open(issues_with_notes_json_path, 'w', encoding='utf-8') as file:
        json.dump(issues, file, ensure_ascii=False, indent=4)

    # 处理和写入CSV文件
    csv_file_path = os.path.join(output_dir, f'issues_with_notes_and_images_{project_id}.csv')
    with open(csv_file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # 写入表头
        writer.writerow([
            'Issue ID', 'Title', 'Description', 'State', 'Created At', 'Updated At', 'Closed At',
            'Author', 'Assignee', 'Labels', 'Milestone', 'Due Date', 'Web URL', 'Note ID', 'Note Body', 'Note Author', 'Note Created At'
        ])

        all_image_urls = []

        # 写入每个issue和其评论的数据
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
                    writer.writerow(issue_base_data + [note['id'], note['body'], note['author']['username'], note['created_at']])
                    all_image_urls.extend(find_image_urls(note['body']))
            else:
                writer.writerow(issue_base_data + ['', '', '', ''])

    print(f"成功将项目 {project_id} 的issues数据保存到了 {csv_file_path}")

    # 提取图片URL并下载图片
    print(f"开始下载项目 {project_id} 的issues中的附件")

    for image_url in all_image_urls:
        full_image_url = f'{project_web_url}{image_url}'
        image_response = requests.get(full_image_url, headers=headers)
        if image_response.status_code == 200:
            image_path = os.path.join(image_dir, *image_url.split('/'))
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            with open(image_path, 'wb') as image_file:
                image_file.write(image_response.content)
                print(f"成功保存 {image_path}")
        else:
            print(f"获取图片失败: {full_image_url}, 状态码: {image_response.status_code}")
        time.sleep(0.2)  # 避免触发API速率限制
    print(f"项目 {project_id} 的所有附件已下载完成")


def main():
    parser = argparse.ArgumentParser(description='Download GitLab issues and notes for specified projects.')
    parser.add_argument('--url', required=True, help='GitLab base URL')
    parser.add_argument('--session', required=True, help='GitLab session cookie')
    parser.add_argument('--ids', required=True, help='Comma-separated list of project IDs')
    parser.add_argument('-o', '--output', default='results', help='Directory to save all output files')

    args = parser.parse_args()

    project_ids = args.ids.split(',')

    for project_id in project_ids:
        print(f'正在处理项目 {project_id}')
        download_issues_and_notes(args.url, args.session, project_id, args.output)
        print(f'完成处理项目 {project_id}')


if __name__ == '__main__':
    main()
