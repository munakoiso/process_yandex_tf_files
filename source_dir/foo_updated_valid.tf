resource "yandex_mdb_postgresql_cluster" "foo" {
  name        = "foo"
  environment = "PRODUCTION"
  network_id  = yandex_vpc_network.infra.id

  config {
    version = 14
    resources {
      resource_preset_id = "s2.micro"
      disk_type_id       = "network-ssd"
      disk_size          = 50
    }
  }

  host {
    zone      = "ru-central1-a"
    subnet_id = yandex_vpc_subnet.infra-db-a.id
  }
  host {
    zone      = "ru-central1-b"
    subnet_id = yandex_vpc_subnet.infra-db-b.id
  }
  host {
    zone      = "ru-central1-c"
    subnet_id = yandex_vpc_subnet.infra-db-c.id
  }
}

resource "yandex_mdb_postgresql_user" "foo-foo-user" {
  cluster_id = yandex_mdb_postgresql_cluster.foo.id
  name     = "foo-user"
  password = random_password.foo_db_pass.result

}

resource "yandex_mdb_postgresql_database" "foo-foo-db" {
  cluster_id = yandex_mdb_postgresql_cluster.foo.id
  name       = "foo-db"
  owner      = "foo-user"
  lc_collate = "en_US.UTF-8"
  lc_type    = "en_US.UTF-8"
  extension {
    name = "pg_stat_statements"
  }
}

resource "yandex_mdb_mysql_cluster" "bar" {
  name        = "bar"
  environment = "PRODUCTION"
  network_id  = yandex_vpc_network.infra.id

  config {
    version = 14
    resources {
      resource_preset_id = "s2.micro"
      disk_type_id       = "network-ssd"
      disk_size          = 50
    }
  }

  host {
    zone      = "ru-central1-a"
    subnet_id = yandex_vpc_subnet.infra-db-a.id
  }
  host {
    zone      = "ru-central1-b"
    subnet_id = yandex_vpc_subnet.infra-db-b.id
  }
  host {
    zone      = "ru-central1-c"
    subnet_id = yandex_vpc_subnet.infra-db-c.id
  }
}

resource "yandex_mdb_mysql_user" "bar-bar-user" {
  cluster_id = yandex_mdb_mysql_cluster.bar.id
  name     = "bar-user"
  password = random_password.bar_db_pass.result

}

resource "yandex_mdb_mysql_database" "bar-bar-db" {
  cluster_id = yandex_mdb_mysql_cluster.bar.id
  name       = "bar-db"
  owner      = "bar-user"
}
