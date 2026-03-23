using System;
using System.Collections.Generic;
using System.Linq;
using Data.TableScript;

namespace Data
{
    public abstract class ConfigDataBase<T> : IConfigDataBase where T : IConfigRawInfo
    {
        private Dictionary<int, T> _data;
        private bool _loaded;
        private string _name;
        
        public void Load()
        {
            _name = typeof(T).Name.Replace("Info", "Config");
            _data = ConfigManager.DeserializeConfigData<Dictionary<int, T>>(_name) ?? new Dictionary<int, T>();
            _loaded = true;
        }

        public T GetData(int id)
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            if (_data.TryGetValue(id, out var info))
            {
                return info;
            }

            throw new KeyNotFoundException($"未找到ID为{id}的{_name}数据");
        }

        public IEnumerable<TResult> SelectValueCollection<TResult>(Func<T, TResult> selector)
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            return _data.Values.Select(selector);
        }

        public IEnumerable<T> GetCollection(Func<T, bool> predicate)
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            return _data.Values.Where(predicate);
        }

        public virtual T GetDataByKey<TEnum>(TEnum key) where TEnum : Enum
        {
            throw new NotImplementedException($"当前配置表类{_name}不支持通过枚举类型获取数据，请在子类中重写该方法");
        }

        public Dictionary<int, string> GetDisplayMap()
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            // name 字段是可选的：存在则显示 "id - name"，否则仅显示 id。
            var nameProperty = typeof(T).GetProperty("name");
            return _data.ToDictionary(kv => kv.Key, kv =>
            {
                if (nameProperty != null)
                {
                    var raw = nameProperty.GetValue(kv.Value)?.ToString();
                    if (!string.IsNullOrEmpty(raw))
                    {
                        return $"{kv.Key} - {raw}";
                    }
                }

                return kv.Key.ToString();
            });
        }

        // --- 以下为 IConfigDataBase 的显式实现（用于非泛型访问） ---
        IConfigRawInfo IConfigDataBase.GetData(int id) => GetData(id);

        IEnumerable<IConfigRawInfo> IConfigDataBase.GetCollection(Func<IConfigRawInfo, bool> predicate)
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            // 这里将 T 作为 IConfigRawInfo 传入 predicate
            return _data.Values.Where(v => predicate(v)).Cast<IConfigRawInfo>();
        }

        IEnumerable<TResult> IConfigDataBase.SelectValueCollection<TResult>(Func<IConfigRawInfo, TResult> selector)
        {
            if (!_loaded)
            {
                throw new InvalidOperationException($"{_name} 数据未加载");
            }

            // selector 接受 IConfigRawInfo，v (T) 可以直接传入
            return _data.Values.Select(v => selector(v));
        }
    }
}
