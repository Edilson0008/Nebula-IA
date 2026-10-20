drop table if exists messages;
drop table if exists conversations;
drop table if exists memories;

create table conversations (
  id          bigint generated always as identity primary key,
  owner       text        not null,
  title       text        not null,
  project     text,
  created_at  text        not null,
  updated_at  text        not null
);

create table messages (
  id              bigint generated always as identity primary key,
  conversation_id bigint not null references conversations(id) on delete cascade,
  role            text   not null check (role in ('user', 'model')),
  content         text   not null,
  attachments     text,
  created_at      text   not null
);

create table memories (
  id              bigint generated always as identity primary key,
  owner           text   not null,
  conversation_id bigint,
  content         text   not null,
  embedding       text   not null,
  created_at      text   not null
);

create index idx_conversations_owner  on conversations (owner, id desc);
create index idx_messages_conversation on messages (conversation_id, id);
create index idx_memories_owner        on memories (owner);
