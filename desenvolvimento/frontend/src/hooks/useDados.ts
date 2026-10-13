import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

const UM_MINUTO = 60_000

export const useEstacoes = () =>
  useQuery({ queryKey: ['estacoes'], queryFn: api.estacoes, staleTime: 10 * UM_MINUTO })

/** Dado ao vivo: atualiza a cada minuto e ao voltar para a aba. */
export const useNivelAtual = (codigo: string) =>
  useQuery({
    queryKey: ['nivel-atual', codigo],
    queryFn: () => api.nivelAtual(codigo),
    refetchInterval: UM_MINUTO,
    refetchOnWindowFocus: true,
  })

export const useChuvaAcumulada = () =>
  useQuery({
    queryKey: ['chuva-acumulada'],
    queryFn: api.chuvaAcumulada,
    refetchInterval: UM_MINUTO,
    refetchOnWindowFocus: true,
  })

export const useAlertasVigentes = () =>
  useQuery({
    queryKey: ['alertas-vigentes'],
    queryFn: api.alertasVigentes,
    refetchInterval: UM_MINUTO,
    refetchOnWindowFocus: true,
  })

export const useSerie = (codigo: string, horas: number) =>
  useQuery({
    queryKey: ['serie', codigo, horas],
    queryFn: () => api.serie(codigo, horas),
    refetchInterval: UM_MINUTO * 2,
    placeholderData: (anterior) => anterior,
  })

export const useCorrelacao = () =>
  useQuery({ queryKey: ['correlacao'], queryFn: api.correlacao, staleTime: 10 * UM_MINUTO })

export const useQualidade = () =>
  useQuery({ queryKey: ['qualidade'], queryFn: api.qualidade, refetchInterval: UM_MINUTO * 2 })

export const usePrevisao = (codigo: string) =>
  useQuery({
    queryKey: ['previsao', codigo],
    queryFn: () => api.previsao(codigo),
    refetchInterval: UM_MINUTO * 5,
  })
