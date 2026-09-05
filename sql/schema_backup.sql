-- Active: 1783824179028@@127.0.0.1@3306@winwin
-- ============================================
-- 数据库 win 表结构导出（含触发器）
-- 生成方式: python scripts/export_schema.py
-- 重建步骤:
--   1. DROP DATABASE `win`;
--   2. CREATE DATABASE `win` DEFAULT CHARSET utf8mb4;
--   3. USE `win`;
--   4. source data/schema_backup.sql
-- ============================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table: agent_sessions
-- ----------------------------
DROP TABLE IF EXISTS `agent_sessions`;
CREATE TABLE `agent_sessions` (
  `id` varchar(32) NOT NULL,
  `user_id` int NOT NULL,
  `title` varchar(200) DEFAULT '',
  `summary` text,
  `agent_type` varchar(20) DEFAULT 'simple',
  `message_count` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: commission_configs
-- ----------------------------
DROP TABLE IF EXISTS `commission_configs`;
CREATE TABLE `commission_configs` (
  `strategy_id` varchar(20) NOT NULL,
  `commission_rate` decimal(10,8) NOT NULL DEFAULT '0.00030000',
  `stamp_tax_rate` decimal(10,8) NOT NULL DEFAULT '0.00050000',
  `transfer_fee_rate` decimal(10,8) NOT NULL DEFAULT '0.00001000',
  `min_commission` decimal(10,4) NOT NULL DEFAULT '5.0000',
  PRIMARY KEY (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: daily_account_snapshot
-- ----------------------------
DROP TABLE IF EXISTS `daily_account_snapshot`;
CREATE TABLE `daily_account_snapshot` (
  `strategy_id` varchar(20) NOT NULL,
  `snapshot_date` date NOT NULL,
  `total_assets` decimal(16,4) DEFAULT NULL,
  `available_cash` decimal(16,4) DEFAULT NULL,
  `frozen_cash` decimal(16,4) DEFAULT NULL,
  `position_value` decimal(16,4) DEFAULT NULL,
  `position_cost` decimal(16,4) DEFAULT NULL,
  `position_count` int DEFAULT NULL,
  `order_count` int DEFAULT NULL,
  `commission` decimal(16,4) DEFAULT NULL,
  PRIMARY KEY (`strategy_id`,`snapshot_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: day_t_records
-- ----------------------------
DROP TABLE IF EXISTS `day_t_records`;
CREATE TABLE `day_t_records` (
  `strategy_id` varchar(20) NOT NULL,
  `stock_code` varchar(20) NOT NULL,
  `trade_date` date NOT NULL,
  `buy_volume` int DEFAULT NULL,
  `buy_amount` decimal(16,4) DEFAULT NULL,
  `buy_count` int DEFAULT NULL,
  `avg_buy_price` decimal(16,4) DEFAULT NULL,
  `sell_volume` int DEFAULT NULL,
  `sell_amount` decimal(16,4) DEFAULT NULL,
  `sell_count` int DEFAULT NULL,
  `avg_sell_price` decimal(16,4) DEFAULT NULL,
  `t_volume` int DEFAULT NULL,
  `t_profit` decimal(16,4) DEFAULT NULL,
  `t_return_rate` decimal(10,4) DEFAULT NULL,
  `holding_change` int DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`strategy_id`,`stock_code`,`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: lots
-- ----------------------------
DROP TABLE IF EXISTS `lots`;
CREATE TABLE `lots` (
  `strategy_id` varchar(20) NOT NULL,
  `stock_code` varchar(20) NOT NULL,
  `lot_size` int DEFAULT NULL,
  `open_time` timestamp NOT NULL,
  `open_price` decimal(16,4) DEFAULT NULL,
  PRIMARY KEY (`strategy_id`,`stock_code`,`open_time`),
  CONSTRAINT `lots_ibfk_1` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: orders
-- ----------------------------
DROP TABLE IF EXISTS `orders`;
CREATE TABLE `orders` (
  `client_order_id` varchar(31) NOT NULL,
  `strategy_id` varchar(20) NOT NULL,
  `account_type` int DEFAULT NULL,
  `account_id` varchar(20) DEFAULT '',
  `stock_code` varchar(20) NOT NULL DEFAULT '',
  `broker_order_id` varchar(30) DEFAULT '',
  `order_sysid` varchar(30) DEFAULT '',
  `order_time` timestamp NULL DEFAULT NULL,
  `order_type` int NOT NULL,
  `price_type` int DEFAULT NULL,
  `price` decimal(16,4) NOT NULL,
  `traded_amount` decimal(16,4) NOT NULL,
  `order_volume` int NOT NULL,
  `traded_volume` int NOT NULL DEFAULT '0',
  `traded_price` decimal(16,4) NOT NULL DEFAULT '0.0000',
  `commission` decimal(16,4) NOT NULL DEFAULT '0.0000',
  `order_status` int NOT NULL,
  `status_msg` text,
  `order_remark` text,
  PRIMARY KEY (`client_order_id`),
  KEY `idx_order_time` (`order_time`),
  KEY `idx_strategy_id` (`strategy_id`),
  CONSTRAINT `orders_ibfk_1` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: positions
-- ----------------------------
DROP TABLE IF EXISTS `positions`;
CREATE TABLE `positions` (
  `strategy_id` varchar(20) NOT NULL,
  `stock_code` varchar(20) NOT NULL,
  `total` int DEFAULT NULL,
  `available` int DEFAULT NULL,
  `frozen` int DEFAULT NULL,
  `unavailable` int DEFAULT NULL,
  `avg_price` decimal(16,4) DEFAULT NULL,
  `remark` text,
  `today` date NOT NULL,
  `first_buy_time` timestamp NULL DEFAULT NULL,
  `sold_out_time` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`strategy_id`,`stock_code`,`today`),
  KEY `idx_strategy_stock_today` (`strategy_id`,`stock_code`,`today`),
  CONSTRAINT `positions_ibfk_1` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: settlements
-- ----------------------------
DROP TABLE IF EXISTS `settlements`;
CREATE TABLE `settlements` (
  `strategy_id` varchar(20) NOT NULL,
  `stock_code` varchar(20) NOT NULL,
  `first_buy_time` timestamp NOT NULL,
  `total_buy_volume` int NOT NULL,
  `total_buy_amount` decimal(16,4) NOT NULL,
  `total_sell_volume` int DEFAULT '0',
  `total_sell_amount` decimal(16,4) DEFAULT '0.0000',
  `avg_cost_price` decimal(16,4) DEFAULT NULL,
  `realized_profit` decimal(16,4) DEFAULT '0.0000',
  `profit_rate` decimal(10,4) DEFAULT '0.0000',
  `is_closed` tinyint(1) DEFAULT '0',
  `close_time` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`strategy_id`,`stock_code`,`first_buy_time`),
  CONSTRAINT `settlements_ibfk_1` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: strategy_users
-- ----------------------------
DROP TABLE IF EXISTS `strategy_users`;
CREATE TABLE `strategy_users` (
  `user_id` int NOT NULL,
  `strategy_id` varchar(20) NOT NULL,
  `can_trade` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`user_id`,`strategy_id`),
  KEY `strategy_id` (`strategy_id`),
  CONSTRAINT `strategy_users_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `strategy_users_ibfk_2` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: strategys
-- ----------------------------
DROP TABLE IF EXISTS `strategys`;
CREATE TABLE `strategys` (
  `strategy_id` varchar(20) NOT NULL,
  `name` varchar(50) DEFAULT NULL,
  `description` text,
  `trade_mode` tinyint DEFAULT NULL,
  `initial_cash` decimal(16,4) DEFAULT NULL,
  `available_cash` decimal(16,4) DEFAULT NULL,
  `frozen_cash` decimal(16,4) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `is_deleted` tinyint DEFAULT '0' COMMENT '0=正常, 1=已删除',
  `detail` text COMMENT '策略详情/详细说明',
  `owner_id` int DEFAULT NULL COMMENT '策略所有者用户ID',
  PRIMARY KEY (`strategy_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: trades
-- ----------------------------
DROP TABLE IF EXISTS `trades`;
CREATE TABLE `trades` (
  `traded_id` varchar(30) NOT NULL,
  `strategy_id` varchar(20) NOT NULL,
  `client_order_id` varchar(31) NOT NULL,
  `broker_order_id` varchar(30) DEFAULT '',
  `order_sysid` varchar(30) DEFAULT '',
  `account_type` int DEFAULT NULL,
  `account_id` varchar(20) DEFAULT '',
  `stock_code` varchar(20) NOT NULL DEFAULT '',
  `order_type` int NOT NULL,
  `traded_time` timestamp NULL DEFAULT NULL,
  `traded_price` decimal(16,4) NOT NULL,
  `traded_volume` int NOT NULL,
  `traded_amount` decimal(16,4) NOT NULL,
  `order_remark` text,
  PRIMARY KEY (`traded_id`),
  KEY `client_order_id` (`client_order_id`),
  KEY `idx_traded_time` (`traded_time`),
  KEY `idx_strategy_id` (`strategy_id`),
  CONSTRAINT `trades_ibfk_1` FOREIGN KEY (`strategy_id`) REFERENCES `strategys` (`strategy_id`),
  CONSTRAINT `trades_ibfk_2` FOREIGN KEY (`client_order_id`) REFERENCES `orders` (`client_order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: user_tool_permissions
-- ----------------------------
DROP TABLE IF EXISTS `user_tool_permissions`;
CREATE TABLE `user_tool_permissions` (
  `user_id` int NOT NULL,
  `tool_key` varchar(32) NOT NULL,
  `enabled` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`user_id`,`tool_key`),
  CONSTRAINT `user_tool_permissions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Table: users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(20) DEFAULT 'viewer',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 当前无触发器

SET FOREIGN_KEY_CHECKS = 1;