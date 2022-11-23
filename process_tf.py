#!/usr/bin/python

from argparse import ArgumentParser
from collections import defaultdict
from os import listdir
from os.path import isfile, join
from json import load

dbs_by_owner = defaultdict(list)
TFSTATE = 'terraform.tfstate'

cluster_types = ['yandex_mdb_postgresql_cluster', 'yandex_mdb_mysql_cluster']

db_resource_by_cluster_type = {
    'yandex_mdb_postgresql_cluster': 'yandex_mdb_postgresql_database',
    'yandex_mdb_mysql_cluster': 'yandex_mdb_mysql_database',
}

user_resource_by_cluster_type = {
    'yandex_mdb_postgresql_cluster': 'yandex_mdb_postgresql_user',
    'yandex_mdb_mysql_cluster': 'yandex_mdb_mysql_user',
}


def get_args():
    parser = ArgumentParser()
    parser.add_argument('-s', '--source-directory', type=str, help="Name of the source directory with .tf files")
    parser.add_argument('--suffix', type=str, help="Suffix of generated .tf files")

    return parser.parse_args()


def get_brackets_sum(line):
    return line.count('{') - line.count('}')


def iterate_til_closing_bracket(lines, index):
    """
    Iterates from lines[index] to line, which contains brackets with same level
    """
    between_brackets = []
    b_sum = 0
    for i in range(index, len(lines)):
        line = lines[i]
        between_brackets.append(line)
        b_sum += get_brackets_sum(line)
        if b_sum == 0:
            return between_brackets, i
    raise Exception(
        f"Can not parse line:\n{lines[index]}",
    )


def prepare_db(db_lines, cluster_resource_type, cluster_resource_name):
    """
    Generates database resource from database in cluster_resource
    """
    prefix_length = db_lines[0].find('database')
    db_name = None
    db_owner = None
    new_db_lines = []
    for i in range(len(db_lines)):
        db_lines[i] = db_lines[i][prefix_length:]
    i = 0

    while i < len(db_lines):
        splitted_line = db_lines[i].split()
        if len(splitted_line) == 3 and splitted_line[0] == 'name' and splitted_line[1] == '=':
            db_name = splitted_line[2]
            if db_name[0] == db_name[-1] == '"' or db_name[0] == db_name[-1] == "'":
                db_name = db_name[1:-1]
        if len(splitted_line) == 3 and splitted_line[0] == 'owner' and splitted_line[1] == '=':
            db_owner = splitted_line[2]
            if db_owner[0] == db_owner[-1] == '"' or db_owner[0] == db_owner[-1] == "'":
                db_owner = db_owner[1:-1]
        if len(splitted_line) == 2 and splitted_line[0] == 'extension' and splitted_line[1] == '{':
            extensions, i = iterate_til_closing_bracket(db_lines, i)
            new_db_lines += extensions
            i += 1
            continue
        new_db_lines.append(db_lines[i])
        i += 1
    if not db_name or not db_owner:
        raise Exception(f"Can not find out db name/owner in {cluster_resource_type} {cluster_resource_name}")
    resource_type = db_resource_by_cluster_type.get(cluster_resource_type, 'unknown_db_resource')
    resource_name = f'{cluster_resource_name}-{db_name}'
    db_lines[0] = f'resource "{resource_type}" "{resource_name}" {{'
    cluster_id_line = f'  cluster_id = {cluster_resource_type}.{cluster_resource_name}.id'
    db_lines = [db_lines[0], cluster_id_line] + db_lines[1:]
    dbs_by_owner[cluster_resource_name, db_owner].append(db_name)
    return db_lines, (cluster_resource_type, cluster_resource_name, resource_type, resource_name, db_name)


def prepare_permissions(permissions, dbs_to_exclude):
    """
    Generates new permissions, without databases owned by current user
    """
    new_permissions = []
    permissions_count = 0
    for i in range(len(permissions)):
        line = permissions[i]
        splitted_line = line.split()
        if len(splitted_line) == 3 and splitted_line[0] == 'database_name' and splitted_line[1] == '=':
            db_name = splitted_line[2]
            if db_name[0] == db_name[-1] == '"' or db_name[0] == db_name[-1] == "'":
                db_name = db_name[1:-1]
            if db_name in dbs_to_exclude:
                continue
        if i != 0 and i != len(permissions) - 1:
            permissions_count += 1
        new_permissions.append(line)
    if permissions_count == 0:
        return ('\n',)
    return new_permissions


def prepare_user(user_lines, cluster_resource_type, cluster_resource_name):
    """
    Generates user resource from user in cluster_resource
    """
    prefix_length = user_lines[0].find('user')
    user_name = None
    new_user_lines = []
    for i in range(len(user_lines)):
        user_lines[i] = user_lines[i][prefix_length:]
    i = 0

    while i < len(user_lines):
        splitted_line = user_lines[i].split()
        if len(splitted_line) == 2 and splitted_line[0] == 'permission' and splitted_line[1] == '{':
            permissions, i = iterate_til_closing_bracket(user_lines, i)
            for line in prepare_permissions(permissions, dbs_by_owner[cluster_resource_name, user_name]):
                new_user_lines.append(line)
            i += 1
            continue
        if len(splitted_line) == 3 and splitted_line[0] == 'name' and splitted_line[1] == '=':
            user_name = splitted_line[2]
            if user_name[0] == user_name[-1] == '"' or user_name[0] == user_name[-1] == "'":
                user_name = user_name[1:-1]
        new_user_lines.append(user_lines[i])
        i += 1

    if not user_name:
        raise Exception(f"Can not find out db name in {cluster_resource_type} {cluster_resource_name}")
    resource_type = user_resource_by_cluster_type.get(cluster_resource_type, 'unknown_user_resource')
    resource_name = f'{cluster_resource_name}-{user_name}'
    new_user_lines[0] = f'resource "{resource_type}" "{resource_name}" {{'
    cluster_id_line = f'  cluster_id = {cluster_resource_type}.{cluster_resource_name}.id'
    new_user_lines = [new_user_lines[0], cluster_id_line] + new_user_lines[1:]
    return new_user_lines, (cluster_resource_type, cluster_resource_name, resource_type, resource_name, user_name)


def cut_out_dbs_and_users(cluster_lines):
    """
    Generates new cluster, user, database resources from cluster resource
    """
    splitted_line = cluster_lines[0].split('"')
    r_type = splitted_line[1]
    r_name = splitted_line[3]
    i = 0
    new_cluster = []
    dbs = []
    raw_users_with_info = []
    users = []
    new_resources = []
    while i < len(cluster_lines):
        line = cluster_lines[i]
        splitted_line = line.split()
        if len(splitted_line) and 'database' == splitted_line[0]:
            db, i = iterate_til_closing_bracket(cluster_lines, i)
            db, resource = prepare_db(db, r_type, r_name)
            dbs.append(db)
            new_resources.append(resource)
        elif len(splitted_line) and 'user' == splitted_line[0]:
            user, i = iterate_til_closing_bracket(cluster_lines, i)
            raw_users_with_info.append((user, r_type, r_name))
        else:
            new_cluster.append(line)
        i += 1
    for user_lines, r_type, r_name in raw_users_with_info:
        user, resource = prepare_user(user_lines, r_type, r_name)
        new_resources.append(resource)
        users.append(user)

    for element in users + dbs:
        new_cluster.append('\n')
        for line in element:
            new_cluster.append(line)
    return new_cluster, new_resources


def process(tf):
    """
    Generates new .tf file lines from old ones
    """
    i = 0
    new_tf = []
    new_resources = []
    while i < len(tf):
        line = tf[i]
        cluster_type_in_line = False
        for cluster_type in cluster_types:
            if f'"{cluster_type}"' in line or f"'{cluster_type}'" in line:
                cluster_type_in_line = True
                break
        if cluster_type_in_line:
            cluster, i = iterate_til_closing_bracket(tf, i)
            cluster_lines, current_new_resources = cut_out_dbs_and_users(cluster)
            new_tf += cluster_lines
            new_resources += current_new_resources
        else:
            new_tf.append(line)
        i += 1
    prev_line_empty = False
    new_tf_less_empty_lines = []
    for i in range(len(new_tf)):
        line = new_tf[i]
        line = line.rstrip()
        if len(line.strip()) == 0:
            if prev_line_empty:
                continue
            prev_line_empty = True
        else:
            prev_line_empty = False
        new_tf_less_empty_lines.append(line)
    return new_tf_less_empty_lines, new_resources


def process_file(file, dest_file):
    new_resources = []
    with open(file, 'r') as file:
        tf = file.readlines()
    new_tf, current_new_resources = process(tf)
    if len(current_new_resources) == 0:
        return []
    new_resources += current_new_resources
    with open(dest_file, 'w') as file:
        file.write('\n'.join(new_tf) + '\n')
    return new_resources


def process_directory(source_dir, suffix):
    tf_files = [f for f in listdir(source_dir) if isfile(join(source_dir, f)) and f[-3:] == '.tf']
    new_resources = []
    for file in tf_files:
        try:
            new_resources += process_file(source_dir + file, (source_dir + file)[:-3] + suffix + '.tf')
        except Exception as exc:
            print(f'Failed to process file {source_dir + file}\n{exc}')
    return new_resources


def print_tf_commands(source_file, new_resources):
    with open(source_file, 'r') as tfstate:
        state = load(tfstate)
    cluster_ids = dict()
    for resource in state.get('resources', []):
        type = resource.get('type', None)
        name = resource.get('name', None)
        id = None
        if type not in cluster_types:
            continue
        for instance in resource['instances']:
            if 'attributes' in instance and 'id' in instance['attributes']:
                id = instance['attributes']['id']
                break
        cluster_ids[(type, name)] = id
    commands = []
    for cluster_type, cluster_name, resource_type, resource_name, name in new_resources:
        cluster_id = cluster_ids.get((cluster_type, cluster_name))
        if not cluster_id:
            print(f'{cluster_type} {cluster_name} id is not found for new resource {resource_type}.{resource_name}')
            continue
        commands.append(f'terraform import {resource_type} {cluster_id}:{name}')
    print('Terraform commands to apply changes:')
    print('\n'.join(commands))


if __name__ == '__main__':
    args = get_args()
    source_dir = args.source_directory
    if source_dir[-1] != '/':
        source_dir += '/'
    new_resources = process_directory(source_dir, args.suffix)
    print_tf_commands(source_dir + TFSTATE, new_resources)
    print('Done')
