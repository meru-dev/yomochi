"use client"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"

interface CategoryItem {
  id: string
  name: string
  icon: string | null
  color: string | null
  is_system: boolean
  parent_id: string | null
  type: string
}

interface CategoriesData {
  items: CategoryItem[]
}

interface CreateCategoryBody {
  name: string
  type: string
  parent_id?: string | null
  color?: string | null
  icon?: string | null
}

export function useCreateCategory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CreateCategoryBody) => {
      const { data, error } = await api.POST("/api/v1/categories", { body })
      if (error) throw error
      return data
    },
    onMutate: async (body: CreateCategoryBody) => {
      await qc.cancelQueries({ queryKey: keys.categories.list() })
      const prev = qc.getQueryData<CategoriesData>(keys.categories.list())
      const optimistic: CategoryItem = {
        id: `opt-${Date.now()}`,
        name: body.name,
        type: body.type,
        color: body.color ?? null,
        icon: body.icon ?? null,
        parent_id: body.parent_id ?? null,
        is_system: false,
      }
      qc.setQueryData<CategoriesData>(keys.categories.list(), (old) =>
        old ? { ...old, items: [...old.items, optimistic] } : { items: [optimistic] }
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.categories.list(), ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.categories.list() })
    },
  })
}
