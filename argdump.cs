using System;
class ArgDump { static void Main(string[] args) { for (int i = 0; i < args.Length; i++) Console.WriteLine($"[{i}]={args[i]}"); } }
