/**
 * Every analysed video, searchable.
 *
 * The whole screen is one question asked of PostgreSQL: the text box, the
 * facet menus, the advanced condition tree, the sort and the page are merged
 * into a single request, and what comes back carries the total, the facet
 * counts and the sentence describing what actually ran.
 *
 * The URL holds everything except the condition tree, so a search is
 * pasteable; the tree is what a saved search is for.
 */

import {
  DownloadOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { App, Alert, Button, Card, Dropdown, Space, Tag } from "antd";
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { metaApi } from "@/api/meta";
import { recordsApi } from "@/api/records";
import { savedSearchApi } from "@/api/savedSearches";
import type { QueryNode, RecordQuery, RecordRow } from "@/api/types";
import { PageHeader } from "@/app/AppShell";
import { AdvancedSearchDrawer } from "@/components/explorer/AdvancedSearchDrawer";
import { RecordDrawer } from "@/components/explorer/RecordDrawer";
import { ResultsTable } from "@/components/explorer/ResultsTable";
import { SaveSearchModal, type SaveSearchValues } from "@/components/explorer/SaveSearchModal";
import { SavedSearchDrawer } from "@/components/explorer/SavedSearchDrawer";
import { SearchBar } from "@/components/explorer/SearchBar";
import { EMPTY_FILTERS } from "@/components/explorer/SearchBar";
import { AnalyzeModal } from "@/components/pipeline/AnalyzeModal";
import { useExplorerQuery } from "@/hooks/useExplorerQuery";
import { errorText } from "@/lib/errors";

export default function ExplorerPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const { state, update, toQuery } = useExplorerQuery();
  const [params] = useSearchParams();

  const [tree, setTree] = useState<QueryNode | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [openRecord, setOpenRecord] = useState<string | null>(null);

  const query: RecordQuery = useMemo(
    () => toQuery({ condition_tree: tree }),
    [toQuery, tree],
  );

  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: ({ signal }) => metaApi.fields(signal),
    staleTime: 5 * 60_000,
  });

  const results = useQuery({
    queryKey: ["records", query],
    queryFn: ({ signal }) => recordsApi.search(query, signal),
    placeholderData: (previous) => previous,
  });

  const save = useMutation({
    mutationFn: (values: SaveSearchValues) =>
      savedSearchApi.create({
        name: values.name,
        description: values.description,
        owner: values.owner,
        pinned: values.pinned,
        payload: {
          filters: query.filters,
          query_text: query.query_text,
          condition_tree: tree,
          sort: query.sort,
          order: query.order,
          page_size: query.page_size,
        },
      }),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["saved-searches"] });
      setSaveOpen(false);
      message.success(`Saved "${saved.name}"`);
    },
    onError: (error) => message.error(errorText(error, { action: "save this search" })),
  });

  const download = useCallback(
    async (format: string) => {
      try {
        await recordsApi.export({ ...query, page: 1, format });
        message.success(`Exported as ${format.toUpperCase()}`);
      } catch (error) {
        message.error(errorText(error, { action: "export these records" }));
      }
    },
    [query, message],
  );

  const clear = () => {
    setTree(null);
    update({ filters: EMPTY_FILTERS, page: 1 });
  };

  /**
   * Put a saved question back on screen.
   *
   * The filter bar and the sort travel in the URL, which is what makes a
   * search pasteable; the condition tree does not fit there and is held in
   * state — so applying one is two moves, not one.
   */
  const applySaved = (payload: RecordQuery) => {
    const filters = (payload.filters ?? {}) as Record<string, string>;
    const list = (key: string) => (filters[key] ? String(filters[key]).split(",") : []);
    setTree((payload.condition_tree as QueryNode | null) ?? null);
    update({
      filters: {
        q: payload.query_text ?? "",
        sentiment: list("sentiment"),
        status: list("status"),
        model: list("model"),
      },
      page: 1,
      ...(payload.sort ? { sort: payload.sort } : {}),
      ...(payload.order ? { order: payload.order } : {}),
      ...(payload.page_size ? { pageSize: payload.page_size } : {}),
    });
  };

  // A drill-down from the dashboard arrives as plain query parameters, which
  // `useExplorerQuery` already reads — nothing to do here but say so.
  const drilled = params.get("status") === "partial";

  return (
    <div className="page">
      <PageHeader
        title="Records"
        blurb="Every analysed video, searchable across summary, entities, transcript and on-screen text."
        extra={
          <Space>
            <Button icon={<FolderOpenOutlined />} onClick={() => setSavedOpen(true)}>
              Saved searches
            </Button>
            <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>
              Save search
            </Button>
            <Button icon={<PlusOutlined />} onClick={() => setAnalyzeOpen(true)}>
              Analyse a video
            </Button>
            <Dropdown
              menu={{
                items: (meta.data?.export_formats ?? ["csv", "json"]).map((format) => ({
                  key: format,
                  label: `Export as ${format.toUpperCase()}`,
                  onClick: () => void download(format),
                })),
              }}
            >
              <Button type="primary" icon={<DownloadOutlined />}>
                Export
              </Button>
            </Dropdown>
          </Space>
        }
      />

      {results.error && (
        <Alert
          type="error"
          showIcon
          message="The search failed"
          description={errorText(results.error, { action: "search the records" })}
        />
      )}

      <Card size="small" className="explorer-card">
        <SearchBar
          filters={state.filters}
          facets={results.data?.facets ?? {}}
          meta={meta.data}
          total={results.data?.total ?? 0}
          loading={results.isFetching}
          ruleCount={results.data?.rule_count ?? 0}
          onChange={(filters) => update({ filters })}
          onAdvanced={() => setAdvancedOpen(true)}
          onClear={clear}
        />

        {results.data?.condition_text ? (
          <Alert
            type="info"
            className="condition-strip"
            message={
              <Space size={4} wrap>
                <span>Advanced:</span>
                <code>{results.data.condition_text.trim()}</code>
                <Tag closable onClose={() => setTree(null)}>
                  {results.data.rule_count} rule{results.data.rule_count === 1 ? "" : "s"}
                </Tag>
              </Space>
            }
          />
        ) : null}

        {drilled && (
          <Alert
            type="info"
            className="condition-strip"
            message="Showing only records where at least one service did not answer."
          />
        )}

        <ResultsTable
          page={results.data}
          loading={results.isPending}
          onQueryChange={(next) =>
            update({
              ...(next.page ? { page: next.page } : {}),
              ...(next.page_size ? { pageSize: next.page_size } : {}),
              ...(next.sort ? { sort: next.sort } : {}),
              ...(next.order ? { order: next.order } : {}),
            })
          }
          onOpen={(row: RecordRow) => setOpenRecord(row.id)}
        />
      </Card>

      <AdvancedSearchDrawer
        open={advancedOpen}
        fields={meta.data?.fields ?? results.data?.fields ?? []}
        tree={tree}
        conditionText={results.data?.condition_text ?? ""}
        ruleCount={results.data?.rule_count ?? 0}
        onApply={(next) => {
          setTree(next);
          update({ page: 1 });
        }}
        onClose={() => setAdvancedOpen(false)}
      />

      <SaveSearchModal
        open={saveOpen}
        payload={query}
        saving={save.isPending}
        summary={
          results.data?.condition_text
            ? `${results.data.total.toLocaleString()} records · ${results.data.rule_count} advanced rule(s)`
            : `${(results.data?.total ?? 0).toLocaleString()} records match right now.`
        }
        onSave={(values) => save.mutate(values)}
        onCancel={() => setSaveOpen(false)}
      />

      <SavedSearchDrawer
        open={savedOpen}
        onClose={() => setSavedOpen(false)}
        onApply={applySaved}
      />

      <AnalyzeModal
        open={analyzeOpen}
        onClose={() => setAnalyzeOpen(false)}
        onSubmitted={(id) =>
          message.success(
            `Submitted as ${id} — the record appears here once the pipeline has finished it.`,
          )
        }
      />

      <RecordDrawer recordId={openRecord} onClose={() => setOpenRecord(null)} />
    </div>
  );
}
