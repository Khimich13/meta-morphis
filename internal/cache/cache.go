package cache

import (
    "database/sql"
    "encoding/json"
    "errors"
    "time"
    _ "embed"
)

type Cache struct {
    db *sql.DB
}

func NewCache(path string) (*Cache, error) {
    db, err := sql.Open("sqlite", path)
    if err != nil {
        return nil, err
    }

    var schema string

    if _, err := db.Exec(schema); err != nil {
        return nil, err
    }

    return &Cache{db: db}, nil
}